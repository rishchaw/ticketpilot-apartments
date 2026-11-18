"""Operator destinations and preparation must stay explicit and safe."""
from types import SimpleNamespace
import os
import pytest
from scripts import cloud, deploy_gcp, manage_tenants
from scripts.tenant_settings import units_csv

UNITS="1A,1B,2A,2B,2C,3A,3B,3C"
ACCOUNT="123456789012"
IMAGE=ACCOUNT+".dkr.ecr.ap-southeast-1.amazonaws.com/ticketpilot-aws@sha256:"+"a"*64


def args(provider="aws", **changes):
    return SimpleNamespace(**{"provider":provider,"profile":"ticketpilot","project":None,"units":None,**changes})


def test_gcp_preparation_preserves_settings_and_cannot_start_by_accident():
    settings={"paused":False,"apartment_name":"Existing building","apartment_units":"1,2,3,4,5,6,7,8","memory":"1Gi","protect_service":True}
    result=deploy_gcp.deployment_values(SimpleNamespace(project="sample-ticketpilot",region="asia-southeast1",leave_paused=True,apartment_units=UNITS),settings,"digest",True)
    assert result["paused"] is True and result["apartment_units"]==UNITS
    assert result["apartment_name"]==settings["apartment_name"] and result["memory"]=="1Gi" and result["protect_service"]
    assert settings["paused"] is False


def test_gcp_regular_update_preserves_units_and_pause():
    result=deploy_gcp.deployment_values(SimpleNamespace(project="sample-ticketpilot",region="asia-southeast1"),{"paused":True,"apartment_units":UNITS,"apartment_name":"Existing"},"digest",False)
    assert result["paused"] and result["apartment_units"]==UNITS and result["apartment_name"]=="Existing"


@pytest.mark.parametrize("value",["1A,1B",None,"1A,1B,2A,2B,2C,3A,3B,../private","1A,1B,2A,2B,2C,3A,3B,"])
def test_invalid_units_rejected_before_deployment(value):
    with pytest.raises(ValueError): units_csv(value)


@pytest.mark.parametrize("provider",["aws","gcp"])
def test_configuration_flags_only_reach_deploy(provider):
    parsed=cloud.parser().parse_args([provider,"deploy","--apartment-units",UNITS,"--leave-paused","--project","sample-ticketpilot"])
    stage="deploy" if provider=="aws" else "all"
    command=cloud.native_command(__import__("pathlib").Path("/project"),provider,stage,parsed)
    assert command[command.index("--apartment-units")+1]==UNITS and "--leave-paused" in command
    parsed.action="resume"
    with pytest.raises(cloud.CloudError,match="deploy"): cloud.execute(None,parsed)


class AWS:
    def __init__(self,account=ACCOUNT):self.account=account
    def aws(self,selected,*command):
        if command[:2]==("sts","get-caller-identity"):return {"Account":self.account}
        if command[:2]==("lambda","get-function"):return {"Code":{"ResolvedImageUri":IMAGE},"Configuration":{"Environment":{"Variables":{"STORAGE_MODE":"dynamodb","DYNAMODB_TABLE":"ticketpilot-aws-tickets","APARTMENT_UNITS":UNITS}}}}
        if command[:2]==("dynamodb","describe-table"):return {"Table":{"TableArn":"arn:aws:dynamodb:ap-southeast-1:"+ACCOUNT+":table/ticketpilot-aws-tickets"}}
        raise AssertionError("Unexpected cloud operation")


def aws_context():return {"account_id":ACCOUNT,"tenant_auth_release":1,"image_uri":IMAGE}


def test_cloud_admin_profile_strips_ambient_static_keys_and_endpoint_redirects(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID","synthetic-wrong-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY","synthetic-wrong-secret")
    monkeypatch.setenv("AWS_ENDPOINT_URL_DYNAMODB","http://unexpected.invalid")
    env,units=manage_tenants.selected_environment(args(),aws_context(),AWS())
    assert env["AWS_PROFILE"]=="ticketpilot" and env["STORAGE_MODE"]=="dynamodb" and units==UNITS
    assert "AWS_ACCESS_KEY_ID" not in env and "AWS_SECRET_ACCESS_KEY" not in env and "AWS_ENDPOINT_URL_DYNAMODB" not in env
    assert os.environ["AWS_ACCESS_KEY_ID"]=="synthetic-wrong-key"


def test_wrong_aws_account_cannot_administer_tenants():
    with pytest.raises(manage_tenants.AccountOperationError,match="account"):
        manage_tenants.selected_environment(args(),aws_context(),AWS("999999999999"))


def test_unvalidated_cloud_image_cannot_provision():
    with pytest.raises(manage_tenants.AccountOperationError,match="Prepare"):
        manage_tenants.selected_environment(args(),{"tenant_auth_release":0},None)


def test_unit_mismatch_cannot_silently_create_other_accounts():
    with pytest.raises(manage_tenants.AccountOperationError,match="units"):
        manage_tenants.selected_environment(args(units="1,2,3,4,5,6,7,8"),aws_context(),AWS())


def test_gcp_cloud_admin_refuses_emulator_and_key_overrides(monkeypatch):
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST","127.0.0.1:8085")
    with pytest.raises(manage_tenants.AccountOperationError,match="ADC"):
        manage_tenants.selected_environment(args("gcp"),{"tenant_auth_release":1,"project":"sample-ticketpilot"},None)


def test_gcp_cloud_admin_refuses_wrong_project():
    with pytest.raises(manage_tenants.AccountOperationError,match="project"):
        manage_tenants.selected_environment(args("gcp",project="different-project"),{"tenant_auth_release":1,"project":"sample-ticketpilot"},None)


@pytest.mark.parametrize("script",["deploy_aws.py","deploy_gcp.py"])
def test_native_units_validation_imports_work_from_an_unrelated_directory(script,tmp_path):
    import subprocess,sys
    from pathlib import Path
    source=Path(__file__).resolve().parents[1]/"scripts"/script
    command=[sys.executable,str(source),"--stage","deploy","--apartment-units","incomplete"]
    if script=="deploy_gcp.py":command += ["--project","sample-ticketpilot"]
    env=os.environ.copy();env.pop("PYTHONPATH",None)
    result=subprocess.run(command,cwd=tmp_path,env=env,capture_output=True,text=True,timeout=20)
    assert result.returncode!=0 and "eight" in result.stderr.lower()
    assert "ModuleNotFoundError" not in result.stderr


def test_operator_parser_never_echoes_accidental_credential_arguments(capsys):
    with pytest.raises(SystemExit): manage_tenants.main(["aws","provision","--password","FICTIONAL_PRIVATE_MARKER_DO_NOT_ECHO"])
    output=capsys.readouterr()
    assert "FICTIONAL_PRIVATE_MARKER_DO_NOT_ECHO" not in output.out+output.err
