"""Operator controls must preserve intentional cloud, browser and Docker boundaries."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts import control

AWS_URL = "https://abcdefghijklmnop.lambda-url.ap-southeast-1.on.aws"


class FakeRunner:
    def __init__(self, results=None):self.calls,self.results=[],list(results or [])
    def __call__(self,command,**options):
        self.calls.append((list(command),options))
        result=self.results.pop(0) if self.results else SimpleNamespace(returncode=0,stdout="{}",stderr="")
        if isinstance(result,BaseException):raise result
        return result


def result(code=0,output="{}",error=""):
    return SimpleNamespace(returncode=code,stdout=output,stderr=error)


@pytest.fixture
def project(tmp_path):
    root=tmp_path/"TicketPilot demo ! with spaces"
    for name in [".venv/Scripts/python.exe",".venv/bin/python","scripts/cloud.py","scripts/manage_tenants.py","scripts/kubernetes_local.py","scripts/stop_services.py","scripts/validate_kubernetes_local.py"]:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text("fixture")
    return root


def make(project,*,results=None,answers=None):
    runner=FakeRunner(results);opened=[];started=[];output=[];choices=iter(answers or [])
    controller=control.Controller(project,runner=runner,opener=lambda url:opened.append(url),starter=lambda command,**options:started.append((command,options)),input_fn=lambda _:next(choices),output=output.append)
    return controller,runner,opened,started,output


def record(root,provider="gcp",**values):
    path=root/".tools"/(provider+"-deployment.json");path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"project":"demo-control-project","paused":True,"region":"asia-southeast1",**values}) if provider=="gcp" else json.dumps({"paused":True,"region":"ap-southeast-1","url":AWS_URL,**values}))


def test_opening_menu_and_exiting_never_contacts_cloud_opens_browser_or_starts_docker(project):
    c,runner,opened,started,_=make(project,answers=["0"])
    assert control.main([],c)==0
    assert runner.calls==[] and opened==[] and started==[]


def test_local_check_is_noninteractive_and_never_queries_an_engine(project,monkeypatch):
    c,runner,opened,started,output=make(project)
    monkeypatch.setattr(control.shutil,"which",lambda _:None)
    assert control.main(["--check"],c)==0
    report=json.loads(output[-1]);assert report["project_python"] and report["cloud_controls"]
    assert report["cloud_contacted"] is False and report["docker_engine_contacted"] is False
    assert runner.calls==[] and opened==[] and started==[]


def test_help_has_no_operational_side_effects(project,capsys):
    c,runner,opened,started,_=make(project)
    with pytest.raises(SystemExit) as exit:control.main(["--help"],c)
    assert exit.value.code==0 and "--check" in capsys.readouterr().out
    assert not runner.calls and not opened and not started


@pytest.mark.parametrize("provider",["aws","gcp"])
def test_start_only_resumes_using_own_project_python_and_root_cwd(project,monkeypatch,tmp_path,provider):
    monkeypatch.chdir(tmp_path)
    c,runner,_,_,_=make(project)
    assert control.main([provider,"start"],c)==0
    command,options=runner.calls[0]
    assert command[0]==control.project_python(project.resolve())
    assert Path(command[1])==project/"scripts/cloud.py"
    assert command[2:4]==[provider,"resume"] and "deploy" not in command and "build" not in command
    assert options["cwd"]==project.resolve()
    if provider=="aws":assert command[-2:]==["--profile","ticketpilot"]


@pytest.mark.parametrize("provider",["aws","gcp"])
def test_stop_dispatches_pause_without_destroying_or_updating(project,provider):
    c,runner,_,_,_=make(project)
    assert control.main([provider,"stop"],c)==0
    command=runner.calls[0][0]
    assert command[2:4]==[provider,"pause"]
    assert not {"destroy","deploy","reset","start"}.intersection(command)


def test_status_does_not_open_any_dashboard_or_change_state(project):
    c,runner,opened,started,_=make(project)
    assert control.main(["aws","status"],c)==0
    assert runner.calls[0][0][2:4]==["aws","status"]
    assert opened==[] and started==[]


def test_explicit_attestation_retry_only_follows_other_provider_auth_failure(project):
    c,runner,_,_,_=make(project,results=[result(1,error=control.OTHER_AUTH_FAILURE),result()])
    assert control.main(["aws","start","--confirm-other-offline"],c)==0
    assert len(runner.calls)==2
    first,second=runner.calls[0][0],runner.calls[1][0]
    assert "--confirm-other-offline" not in first
    assert second==[*first,"--confirm-other-offline"]


@pytest.mark.parametrize("error",["The other provider is active", "Missing credentials", "Docker is not running"])
def test_attestation_cannot_bypass_unrelated_guard_or_runtime_failures(project,error):
    c,runner,_,_,_=make(project,results=[result(1,error=error)])
    assert control.main(["aws","start","--confirm-other-offline"],c)==1
    assert len(runner.calls)==1


def test_interactive_attestation_needs_typed_operator_confirmation(project):
    c,runner,_,_,_=make(project,results=[result(1,error=control.OTHER_AUTH_FAILURE),result()],answers=["PAUSED"])
    assert c.perform("aws","start",interactive=True)==0 and len(runner.calls)==2
    c,runner,_,_,_=make(project,results=[result(1,error=control.OTHER_AUTH_FAILURE)],answers=[""])
    assert c.perform("aws","start",interactive=True)==1 and len(runner.calls)==1


def test_successful_start_does_not_weaken_its_guard_even_if_attestation_was_permitted(project):
    c,runner,_,_,_=make(project)
    assert control.main(["aws","start","--confirm-other-offline"],c)==0
    assert len(runner.calls)==1 and "--confirm-other-offline" not in runner.calls[0][0]


def test_attestation_flag_is_rejected_for_unrelated_action(project):
    c,runner,_,_,_=make(project)
    assert control.main(["aws","stop","--confirm-other-offline"],c)==1
    assert runner.calls==[]


def test_gcp_old_image_start_failure_explains_prepare_without_performing_it(project):
    c,runner,_,_,output=make(project,results=[result(1,error="Tenant auth image upgrade required")])
    assert control.main(["gcp","start"],c)==1
    assert len(runner.calls)==1 and "deploy" not in runner.calls[0][0]
    assert any("Prepare" in line for line in output)


def test_gcp_prepare_is_explicit_leaves_paused_and_provisions_separately(project):
    record(project)
    c,runner,opened,started,_=make(project)
    assert control.main(["gcp","prepare"],c)==0
    first,second=[call[0] for call in runner.calls]
    assert first[2:4]==["gcp","deploy"] and "--leave-paused" in first
    assert first[first.index("--apartment-units")+1]=="1A,1B,2A,2B,2C,3A,3B,3C"
    assert Path(second[1]).name=="manage_tenants.py" and second[2:]==["gcp","provision"]
    assert not any("resume" in command or "reset" in command for command in (first,second))
    assert not opened and not started


@pytest.mark.parametrize("paused",[False,None])
def test_gcp_prepare_rejects_active_or_unknown_pause_records(project,paused):
    record(project,paused=paused)
    c,runner,_,_,_=make(project)
    assert control.main(["gcp","prepare"],c)==1 and not runner.calls


def test_failed_gcp_prepare_never_runs_account_provision_or_resume(project):
    record(project)
    c,runner,_,_,_=make(project,results=[result(1,error="Fictional failed guarded deployment")])
    assert control.main(["gcp","prepare"],c)==1
    assert len(runner.calls)==1


@pytest.mark.parametrize("provider",["aws","gcp"])
def test_update_is_separate_explicit_deploy_without_account_reset(project,provider):
    c,runner,_,_,_=make(project)
    assert control.main([provider,"update"],c)==0
    command=runner.calls[0][0]
    assert command[2:4]==[provider,"deploy"]
    assert "--leave-paused" not in command and "reset" not in command and "provision" not in command


def test_browser_opens_only_selected_dashboard_and_never_embeds_credentials(project):
    c,runner,opened,started,_=make(project)
    assert control.main(["open","grafana"],c)==0
    assert opened==["http://127.0.0.1:3000"]
    assert not runner.calls and not started
    assert "@" not in opened[0] and "token=" not in opened[0]


def test_gcp_console_infers_private_project_without_auth_or_billing_api_calls(project):
    record(project)
    c,runner,opened,started,_=make(project)
    assert control.main(["open","gcp-cloud-run"],c)==0
    assert "project=demo-control-project" in opened[0] and "/asia-southeast1/" in opened[0]
    assert not runner.calls and not started


def test_invalid_project_or_region_record_cannot_open_or_authenticate_wrong_target(project):
    record(project,project="bad && command")
    c,runner,opened,_,_=make(project)
    assert control.main(["open","gcp-console"],c)==1
    assert not opened and not runner.calls
    record(project,region="another-region")
    assert control.main(["gcp","prepare"],c)==1
    assert not opened and not runner.calls


@pytest.mark.parametrize("url",["https://attacker.invalid/",AWS_URL+"?token=secret",AWS_URL+":bad",AWS_URL+"#private-key"])
def test_portal_opening_rejects_invalid_or_credential_bearing_urls(project,url):
    record(project,"aws",url=url)
    c,runner,opened,_,_=make(project)
    assert control.main(["aws","portal"],c)==1
    assert not opened and not runner.calls


def test_portal_opening_uses_saved_service_with_no_secret_query(project):
    record(project,"aws")
    c,runner,opened,_,_=make(project)
    assert control.main(["aws","portal"],c)==0
    assert opened==[AWS_URL+"/tenant"] and not runner.calls


def test_docker_desktop_is_opened_only_by_selected_local_action(project,monkeypatch):
    c,runner,opened,started,_=make(project)
    monkeypatch.setattr(control,"desktop_command",lambda:["fictional-docker-desktop"])
    assert control.main(["local","docker-open"],c)==0
    assert started==[(["fictional-docker-desktop"],{"cwd":project.resolve()})]
    assert not runner.calls and not opened


def test_kubernetes_forwarding_uses_owned_helper_in_foreground_and_ctrl_c_returns(project):
    c,runner,opened,started,output=make(project,results=[KeyboardInterrupt()])
    assert control.main(["local","k8s-forward-grafana"],c)==0
    command,options=runner.calls[0]
    assert Path(command[1]).name=="kubernetes_local.py" and command[2:]==["forward","grafana"]
    assert options["capture_output"] is False and not started and not opened
    assert any("Ctrl+C" in line for line in output)


def test_stop_all_uses_existing_independent_stop_helper(project):
    c,runner,_,_,_=make(project)
    assert control.main(["stop-all"],c)==0
    command=runner.calls[0][0]
    assert Path(command[1]).name=="stop_services.py" and command[2:]==["--profile","ticketpilot"]


def test_explicit_aws_sign_in_requires_supported_cli_then_verifies_status(project,monkeypatch):
    monkeypatch.setattr(control.shutil,"which",lambda name:"aws" if name=="aws" else None)
    c,runner,opened,_,_=make(project,results=[result(output="aws-cli/2.39.6 Python/3.13"),result(),result()])
    assert control.main(["aws","login"],c)==0
    assert runner.calls[0][0]==["aws","--version"]
    assert runner.calls[1][0]==["aws","login","--profile","ticketpilot"]
    assert runner.calls[1][1]["capture_output"] is False
    assert runner.calls[2][0][2:4]==["aws","status"]
    assert not opened


def test_old_aws_cli_never_runs_login_or_installs_tools(project,monkeypatch):
    monkeypatch.setattr(control.shutil,"which",lambda _:"aws")
    c,runner,_,_,_=make(project,results=[result(output="aws-cli/2.20.0")])
    assert control.main(["aws","login"],c)==1
    assert len(runner.calls)==1


def test_gcp_sign_in_uses_two_browser_dialogs_and_private_project_quota_only(project,monkeypatch):
    record(project)
    monkeypatch.setattr(control,"gcloud_path",lambda _:"gcloud")
    c,runner,opened,_,_=make(project)
    assert control.main(["gcp","login"],c)==0
    commands=[call[0] for call in runner.calls]
    assert commands[0]==["gcloud","--configuration=ticketpilot-gcp","auth","login"]
    assert commands[1]==["gcloud","--configuration=ticketpilot-gcp","auth","application-default","login"]
    assert commands[2][-2:]==["set-quota-project","demo-control-project"]
    assert all(call[1]["env"]["CLOUDSDK_PYTHON"]==control.project_python(project.resolve()) for call in runner.calls)
    assert not any("run" in command or "deploy" in command or "activate" in command for command in commands)
    assert not opened


def test_guide_and_cost_links_do_not_query_cost_explorer_or_provision_services(project):
    c,runner,opened,started,output=make(project)
    assert control.main(["guide"],c)==0
    assert any("Terraform" in line and "no Terraform server" in line for line in output)
    assert control.main(["open","aws-billing"],c)==0
    assert control.main(["open","aws-credits"],c)==0
    assert control.main(["open","aws-budgets"],c)==0
    assert len(opened)==3 and all(url.startswith("https://console.aws.amazon.com/") for url in opened)
    assert not runner.calls and not started


def test_invalid_cli_arguments_do_not_echo_accidentally_supplied_values(project,capsys):
    c,runner,_,_,_=make(project)
    with pytest.raises(SystemExit):control.main(["aws","--password","FICTIONAL-PRIVATE-VALUE"],c)
    captured=capsys.readouterr()
    assert "FICTIONAL-PRIVATE-VALUE" not in captured.err+captured.out and not runner.calls


def test_windows_launcher_resolves_own_directory_with_spaces_and_bang_safely():
    launcher=Path(control.__file__).resolve().parents[1]/"TICKETPILOT.cmd"
    text=launcher.read_text(encoding="utf-8")
    assert "DisableDelayedExpansion" in text and 'pushd "%~dp0"' in text
    assert '".venv\\Scripts\\python.exe" "scripts\\control.py"' in text
    assert "popd" in text and "docker" not in text.casefold() and "cloud.py" not in text


def test_kind_start_creates_only_fictional_accounts_through_existing_validator(project):
    c,runner,opened,started,output=make(project)
    assert control.main(["local","k8s-start"],c)==0
    assert [Path(call[0][1]).name for call in runner.calls]==["kubernetes_local.py","validate_kubernetes_local.py"]
    assert not opened and not started
    assert all("manage_tenants.py" not in str(call[0]) for call in runner.calls)


def test_failed_kind_start_does_not_provision_any_accounts(project):
    c,runner,_,_,_=make(project,results=[result(1)])
    assert control.main(["local","k8s-start"],c)==1 and len(runner.calls)==1


def test_local_stop_never_contacts_a_cloud(project):
    c,runner,_,_,_=make(project)
    assert control.main(["local","stop-local"],c)==0
    assert runner.calls[0][0][2:]==["--local-only"]


def test_docker_status_is_read_only_and_scoped_to_ticketpilot(project,monkeypatch):
    monkeypatch.setattr(control.shutil,"which",lambda _:"docker")
    c,runner,opened,started,_=make(project)
    assert control.main(["local","docker-status"],c)==0
    command=runner.calls[0][0]
    assert command[:3]==["docker","ps","-a"] and "label=com.docker.compose.project=ticketpilot-aws" in command
    assert not opened and not started


@pytest.mark.parametrize("provider", ["aws", "gcp"])
def test_redeploy_builds_without_resuming(project, provider):
    c, runner, *_ = make(project)
    assert control.main([provider, "redeploy"], c) == 0
    assert [call[0][2:4] for call in runner.calls] == [[provider, "deploy"]]


def test_monitoring_local_after_cloud_targets_local_config(project, monkeypatch):
    (project / ".env").touch()
    (project / ".secrets").mkdir()
    (project / ".secrets/metrics-token").touch()
    monkeypatch.setenv("PROMETHEUS_CONFIG", "./monitoring/prometheus/cloud.yml")
    monkeypatch.setattr(control.shutil, "which", lambda _: "docker")
    c, runner, *_ = make(project)
    assert control.main(["local", "monitor-start"], c) == 0
    command, options = runner.calls[0]
    assert command[command.index("up"):] == ["up", "-d", "--no-deps", "--force-recreate", "prometheus", "grafana"]
    assert options["env"]["PROMETHEUS_CONFIG"] == "./monitoring/prometheus/local.yml"


@pytest.mark.parametrize("action,expected", [("app-start", ["up", "-d", "--no-deps", "app"]),
    ("app-rebuild", ["up", "-d", "--build", "--no-deps", "app"]), ("app-stop", ["stop", "app"]),
    ("monitor-stop", ["stop", "prometheus", "grafana"])])
def test_compose_actions_are_scoped_and_keep_volumes(project, monkeypatch, action, expected):
    if action != "app-stop" and action != "monitor-stop":
        (project / ".env").touch()
    monkeypatch.setattr(control.shutil, "which", lambda _: "docker")
    c, runner, *_ = make(project)
    assert control.main(["local", action], c) == 0
    command, _ = runner.calls[0]
    assert command == ["docker", "compose", "-p", "ticketpilot-aws", "-f", str(project.resolve() / "compose.yaml"), "--profile", "local", *expected]


def test_overview_reports_cloud_failure_and_continues_to_local_services(project, monkeypatch):
    monkeypatch.setattr(control.shutil, "which", lambda _: "docker")
    aws = json.dumps({"paused": True, "health_verified": True, "health_http_status": 429})
    c, runner, opened, _, output = make(project, results=[
        result(output=aws), result(code=1), result(output="app Exited"), result(output='{"phase":"stopped"}')])
    assert control.main(["overview"], c) == 1
    report = "\n".join(output)
    for message in ("AWS portal: paused | HTTP 429", "GCP portal: unknown", "app Exited", "Local Kubernetes: stopped"):
        assert message in report
    assert not opened and len(runner.calls) == 4


def test_overview_recognizes_absent_aws_and_verified_gcp(project, monkeypatch):
    monkeypatch.setattr(control.shutil, "which", lambda _: "docker")
    gcp = {"paused": False, "verified_urls": [{"health_http_status": 200}]}
    c, _, _, _, output = make(project, results=[
        result(output='{"deployed":false}'), result(output=json.dumps(gcp)),
        result(), result(output='{"phase":"not_prepared"}')])
    assert control.main(["overview"], c) == 0
    assert any("Lambda function was not found" in line for line in output)
    assert any("GCP portal: enabled | HTTP 200" in line for line in output)


def test_aws_status_stdout_is_a_single_json_document(project, monkeypatch, capsys):
    from scripts import cloud
    runner = cloud.Runner(project)
    monkeypatch.setattr(cloud, "native_command", lambda *args: ["aws-status"])
    monkeypatch.setattr(runner, "run", lambda _: '{"paused":true}')
    assert json.loads(runner.native("aws", "status", None)) == {"paused": True}
    assert capsys.readouterr().out == ""
