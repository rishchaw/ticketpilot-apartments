locals {
  name             = "ticketpilot-aws"
  parameter_prefix = "/ticketpilot-aws"
  ssm_prefix       = "arn:${data.aws_partition.current.partition}:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter${local.parameter_prefix}"
  model_arn        = "arn:${data.aws_partition.current.partition}:bedrock:${var.bedrock_region}::foundation-model/${var.bedrock_model_id}"
}

resource "aws_dynamodb_table" "tickets" {
  name                        = "${local.name}-tickets"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "id"
  deletion_protection_enabled = var.protect_ticket_data
  # Best-effort throughput targets, not a guaranteed request ceiling or budget.
  on_demand_throughput {
    max_read_request_units  = 25
    max_write_request_units = 10
  }
  attribute {
    name = "id"
    type = "S"
  }
  attribute {
    name = "queue"
    type = "S"
  }
  attribute {
    name = "created_at"
    type = "S"
  }
  global_secondary_index {
    name = "recent-tickets"
    key_schema {
      attribute_name = "queue"
      key_type       = "HASH"
    }
    key_schema {
      attribute_name = "created_at"
      key_type       = "RANGE"
    }
    projection_type = "ALL"
    on_demand_throughput {
      max_read_request_units  = 25
      max_write_request_units = 10
    }
  }
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 7
}

resource "aws_iam_role" "runtime" {
  name = "${local.name}-runtime"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "runtime" {
  name = "${local.name}-runtime"
  role = aws_iam_role.runtime.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem"]
        Resource = aws_dynamodb_table.tickets.arn
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:Query"]
        Resource = "${aws_dynamodb_table.tickets.arn}/index/recent-tickets"
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameters"]
        Resource = ["${local.ssm_prefix}/admin-token", "${local.ssm_prefix}/metrics-token"]
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.app.arn}:*"
      }
      ], var.enable_bedrock ? [{
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel"]
        Resource = local.model_arn
    }] : [])
  })
}

resource "aws_lambda_function" "app" {
  function_name                  = local.name
  role                           = aws_iam_role.runtime.arn
  package_type                   = "Image"
  image_uri                      = var.image_uri
  architectures                  = ["x86_64"]
  memory_size                    = 1024
  timeout                        = 30
  reserved_concurrent_executions = var.paused ? 0 : var.reserved_concurrency
  environment {
    variables = {
      STORAGE_MODE              = "dynamodb"
      DYNAMODB_TABLE            = aws_dynamodb_table.tickets.name
      ADMIN_TOKEN_PARAMETER     = "${local.parameter_prefix}/admin-token"
      METRICS_TOKEN_PARAMETER   = "${local.parameter_prefix}/metrics-token"
      LLM_PROVIDER              = var.enable_bedrock ? "bedrock" : "none"
      BEDROCK_MODEL_ID          = var.bedrock_model_id
      BEDROCK_REGION            = var.bedrock_region
      LLM_MAX_CALLS_PER_MINUTE  = "3"
      APARTMENT_NAME            = var.apartment_name
      APARTMENT_UNITS           = var.apartment_units
      APARTMENT_REFRESH_SECONDS = tostring(var.manager_refresh_seconds)
      APARTMENT_QUEUE_LIMIT     = tostring(var.queue_limit)
      OPENBLAS_NUM_THREADS      = "1"
      OMP_NUM_THREADS           = "1"
    }
  }
  depends_on = [aws_iam_role_policy.runtime]
}

resource "aws_lambda_function_url" "app" {
  function_name      = aws_lambda_function.app.function_name
  authorization_type = "NONE"
}

resource "aws_lambda_permission" "url" {
  statement_id           = "PublicFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.app.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "invoke" {
  statement_id             = "InvokeViaFunctionUrlOnly"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.app.function_name
  principal                = "*"
  invoked_via_function_url = true
}

output "service_url" { value = aws_lambda_function_url.app.function_url }
output "function_name" { value = aws_lambda_function.app.function_name }
output "table_name" { value = aws_dynamodb_table.tickets.name }
