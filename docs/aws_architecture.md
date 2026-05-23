# AWS Architecture — ExamPrep Platform
## Module 4: Cloud AWS Hands-on

This document describes how to deploy ExamPrep on AWS following the 3-Tier Hierarchy and C4 Model patterns.

---

## Architecture Diagram (3-Tier Hierarchy)

```
┌─────────────────────────────────────────────────────────────────────┐
│  TIER 1: Presentation                                               │
│  CloudFront (CDN) → S3 (Static Frontend)                           │
└─────────────────────────────────────────────────────────────────────┘
              │
┌─────────────────────────────────────────────────────────────────────┐
│  TIER 2: Application                                                │
│  ALB (Load Balancer) → ECS Fargate Cluster                         │
│    ├── API Service (FastAPI containers)                             │
│    └── Worker Service (Celery containers)                           │
└─────────────────────────────────────────────────────────────────────┘
              │
┌─────────────────────────────────────────────────────────────────────┐
│  TIER 3: Data                                                       │
│  ├── MongoDB Atlas (managed NoSQL)                                  │
│  ├── ElastiCache Redis (managed cache)                              │
│  └── S3 (file storage, backups)                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## VPC Design (B22: Identity & Foundation)

```
VPC: 10.0.0.0/16
├── Public Subnets (2 AZs)
│   ├── 10.0.1.0/24 (us-east-1a) — ALB, NAT Gateway
│   └── 10.0.2.0/24 (us-east-1b) — ALB
├── Private Subnets (2 AZs)
│   ├── 10.0.3.0/24 (us-east-1a) — ECS tasks
│   └── 10.0.4.0/24 (us-east-1b) — ECS tasks
└── Data Subnets (2 AZs)
    ├── 10.0.5.0/24 (us-east-1a) — ElastiCache
    └── 10.0.6.0/24 (us-east-1b) — ElastiCache
```

## IAM Roles (B22)

- `ExamPrepECSTaskRole` — read/write S3, read Secrets Manager
- `ExamPrepECSExecutionRole` — pull from ECR, write CloudWatch logs
- `ExamPrepCIRole` — push to ECR, update ECS service (GitHub Actions OIDC)

## ECS Service (B25: Container Orchestration)

```yaml
# task-definition.json (key excerpts)
family: examprep-api
cpu: 512
memory: 1024
networkMode: awsvpc
requiresCompatibilities: [FARGATE]
containerDefinitions:
  - name: api
    image: <account>.dkr.ecr.us-east-1.amazonaws.com/examprep:latest
    portMappings: [{containerPort: 8000}]
    environment:
      - {name: APP_ENV, value: production}
    secrets:
      - {name: SECRET_KEY, valueFrom: arn:aws:secretsmanager:...}
      - {name: MONGODB_URL, valueFrom: arn:aws:secretsmanager:...}
    logConfiguration:
      logDriver: awslogs
      options:
        awslogs-group: /ecs/examprep
        awslogs-region: us-east-1
```

## CI/CD with CodePipeline (B28)

```
GitHub Push
    │
    ▼
CodePipeline
    ├── Source: GitHub connection
    ├── Build:  CodeBuild
    │     - pip install, pytest
    │     - docker build + push to ECR
    └── Deploy: CodeDeploy (Blue/Green on ECS)
          - Zero-downtime deployment
          - Auto-rollback on health check failure
```

## CloudWatch Monitoring (B29)

Alarms configured:
- `API-HighErrorRate`: ErrorRate > 1% for 5 min → SNS email
- `API-HighLatency`: P99 > 2000ms for 5 min → SNS email
- `ECS-HighCPU`: CPUUtilization > 80% → scale out
- `Redis-LowMemory`: FreeableMemory < 50MB → alert

Dashboard panels:
- Request rate (req/min)
- Error rate (%)
- P50/P95/P99 latency
- Cache hit rate
- Active ECS tasks
- MongoDB connection pool

## Lambda: Async Email (B26: Serverless)

```python
# Triggered by SQS queue when attempt is completed
def handler(event, context):
    for record in event['Records']:
        body = json.loads(record['body'])
        send_results_email(body['user_email'], body['score'], body['exam_title'])
```

## Cost Optimisation (FinOps)

| Service          | Configuration          | Est. Monthly |
|------------------|------------------------|-------------|
| ECS Fargate      | 0.25 vCPU, 0.5GB × 2  | ~$15        |
| ElastiCache      | cache.t3.micro         | ~$13        |
| MongoDB Atlas    | M10 cluster            | ~$57        |
| ALB              | Low traffic            | ~$16        |
| CloudFront       | First 1TB free         | ~$0         |
| **Total**        |                        | **~$100/mo**|

Auto-scaling: ECS scales 2→10 tasks based on CPU > 70%, scales back on CPU < 30%.
