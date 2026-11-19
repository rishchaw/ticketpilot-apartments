# TicketPilot Apartments

Eight households use a mobile portal in English or Filipino to report water interruptions, repairs, billing questions and renewal requests. Each tenant signs in, submits a concern and saves a private tracking link. The manager sees one queue, posts notices, assigns work and sends updates through the portal.

**On the existing Windows PC, double-click `TICKETPILOT.cmd` in the `ticketpilot-aws` folder.** Choose **Check all service statuses (live)** to see which deployment is enabled and which local services are running. To bring the existing AWS site online, choose **AWS controls → Start existing portal**. To publish changed code, choose **Redeploy current code**. [Step-by-step instructions](docs/OPERATIONS_QUICKSTART.md)

| Where to run it | What runs there | Last recorded deployment |
| --- | --- | --- |
| AWS Singapore | Lambda Function URL, DynamoDB, SSM, ECR and CloudWatch | Paused. The tenant-login image and eight accounts were provisioned. Hosted login acceptance is pending a resume. |
| GCP Singapore | Cloud Run, Firestore, Secret Manager, Artifact Registry and Cloud Logging | Paused. Choose **GCP controls → Prepare** to replace the older image and provision GCP accounts before the first Start. |
| Local Docker | The app with SQLite, plus optional Prometheus and Grafana | The menu controls these on this PC. |
| Local Kubernetes | A kind cluster with the app, Prometheus, Grafana and a fictional SQLite volume | Optional portfolio demo. Its Stop control removes the demo data. |

The cloud deployments have separate databases and credentials. Use one provider at a time. Both support the same app source and have their own Terraform configurations. A pause preserves stored data and images, which can still incur charges. [Deployment history](docs/DEPLOYMENT_STATUS.md) · [Cloud design](docs/CLOUD_PORTABILITY.md)

| What you want to do | Guide |
| --- | --- |
| Start, redeploy, stop, monitor or troubleshoot | [Beginner operations guide](docs/OPERATIONS_QUICKSTART.md) |
| Understand which files run and what is optional | [Codebase usage review](docs/CODEBASE_USAGE.md) |
| Set up a fresh development checkout | [Tools and local setup](docs/STACK_GUIDE.md#fresh-clone-setup) |
| Operate one provider | [AWS README.txt](docs/aws/README.txt) · [GCP README.txt](docs/gcp/README.txt) · [Advanced lifecycle commands](docs/PROVIDER_OPERATIONS.md) |
| Inspect either cloud architecture | [AWS diagram](docs/ARCHITECTURE_AWS.md) · [GCP diagram](docs/ARCHITECTURE_GCP.md) |
| Give a resident access or manage a concern | [Tenant access](docs/TENANT_ACCESS.md) · [Apartment workflow](docs/APARTMENT_USE_CASE.md) |
| Use the monitoring dashboards or run the kind demo | [Stack guide](docs/STACK_GUIDE.md) · [Kubernetes](docs/KUBERNETES.md) |
| Review tests, releases or optional AI | [CI/CD](docs/CI_CD.md) · [Validation](docs/VALIDATION.md) · [RAG and Bedrock](docs/RAG_IMPLEMENTATION.md) |

The apartment workflow uses fixed bilingual guidance. The original IT support demo at `/demo` uses a CPU classifier and retrieves articles from 14 packaged runbooks. Its optional Bedrock generation is disabled in the hosted configurations.

[![CI](https://github.com/rishchaw/ticketpilot-apartments/actions/workflows/ci.yml/badge.svg)](https://github.com/rishchaw/ticketpilot-apartments/actions/workflows/ci.yml)
