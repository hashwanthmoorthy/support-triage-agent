# Project Spec: Self-Healing Support Triage Agent

## 1. Purpose
A customer support ticket triage system. Incoming tickets are classified by an LLM-powered agent. Simple tickets are resolved autonomously via tool calls. Ambiguous tickets pause for human approval before any action is taken. Every run is traced for observability. Deployed on AWS as a demo/portfolio project.

## 2. Tech Stack (pinned)
- Python 3.11
- FastAPI (backend API)
- LangChain (latest stable, pin exact version once installed — do not auto-upgrade mid-build)
- LangGraph (latest stable, pin exact version once installed)
- LangSmith (tracing only, via env vars — no custom LangSmith code needed beyond config)
- React + Vite (frontend)
- Docker + docker compose
- GitHub Actions (CI/CD)
- AWS EC2 (single instance, public subnet) — no ECS, no App Runner, no Bedrock, no Terraform for this build
- Anthropic API (Claude) as the LLM provider, called directly — not via Bedrock

## 3. Architecture
```
Frontend (React)
   -> FastAPI backend
        -> LangGraph agent
             -> classify_ticket (LLM call: simple vs ambiguous)
             -> resolve_via_tools (calls MCP tool servers) [if simple]
             -> human_approval (LangGraph interrupt/checkpoint) [if ambiguous]
             -> apply_decision (executes final resolve/route action)
        -> LangSmith (auto-traces every graph run via env vars)
   -> MCP tool servers (mock data): ticket_lookup, knowledge_base_search, send_email (stub)
```

All of the above (backend, agent, MCP servers) runs inside Docker containers on a single EC2 instance. Frontend can be a separate container or served as static build files by the backend — default to separate container via docker-compose for clarity.

## 4. LangGraph Node Details
- **classify_ticket**: input = ticket text. Output = `{category: "simple" | "ambiguous", reasoning: str}`. Single LLM call.
- **resolve_via_tools**: only runs if category == "simple". Calls one or more MCP tools (ticket_lookup, knowledge_base_search) to gather info, then produces a resolution action.
- **human_approval**: only runs if category == "ambiguous". Uses LangGraph's `interrupt()` to pause execution. Graph state is checkpointed. Resumes when a human submits approve/reject via the frontend, which hits a `/resume` API endpoint.
- **apply_decision**: executes the final action (mock "close ticket" / "send response" / "escalate") based on either the auto-resolution or the human's decision.

## 5. MCP Tool Servers (mock data is fine)
- `ticket_lookup(ticket_id)` -> returns a fake JSON ticket record
- `knowledge_base_search(query)` -> returns 1-2 fake KB snippets
- `send_email(to, subject, body)` -> stub, just logs and returns success

## 6. Environment Variables
```
ANTHROPIC_API_KEY=
LANGCHAIN_API_KEY=
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=support-triage-agent
```
Never hardcode these. Never paste real key values into the Claude Code chat — set them directly in `.env` (local) and GitHub Secrets (CI/CD).

## 7. Repo Structure
```
/backend
    /agent          <- LangGraph nodes, graph definition
    /mcp_servers     <- mock tool servers
    main.py          <- FastAPI app
    requirements.txt
    Dockerfile
/frontend
    src/
    package.json
    Dockerfile
docker-compose.yml
.github/workflows/deploy.yml
.env.example
PROJECT_SPEC.md
README.md
```

## 8. Deployment Target
- Single EC2 instance (t3.micro or t3.small), **public subnet**, auto-assigned public IP, no NAT Gateway needed.
- Security group: inbound 22 (SSH, restrict to my IP), inbound 80/443 or app port (frontend/API), outbound all.
- Docker + docker compose installed on the instance (one-time setup).
- Repo `git clone`d once to `/home/ubuntu/app` on first setup.

## 9. CI/CD (GitHub Actions)
- Trigger: push to `main`
- Job: SSH into EC2 (via `appleboy/ssh-action` or similar), run:
  ```
  cd /home/ubuntu/app
  git pull origin main
  docker compose down
  docker compose up -d --build
  ```
- No container registry (ECR) needed — image builds locally on the EC2 box from pulled source.
- Secrets needed in GitHub repo settings: `EC2_HOST`, `EC2_SSH_KEY`, `ANTHROPIC_API_KEY`, `LANGCHAIN_API_KEY`

## 10. Explicitly Out of Scope (do not build unless asked)
- Terraform / infrastructure-as-code
- ECS, App Runner, EKS
- AWS Bedrock
- Container registry (ECR)
- NAT Gateway / private subnets
- Auto-scaling, load balancing, multi-instance setups
- Authentication/authorization on the frontend (demo only)

## 11. Build Order (for Claude Code to follow, one phase at a time)
1. Backend skeleton + LangGraph agent logic (classify -> resolve/human-approval -> apply). Test locally via script/curl, no frontend yet.
2. MCP tool servers (mock data). Test tool calls in isolation.
3. LangSmith wiring. Confirm traces appear.
4. Frontend. Build against working backend API.
5. Dockerfile + docker-compose. Test locally (`docker compose up`) before touching AWS.
6. EC2 provisioning + first manual deploy (SSH in, clone, `docker compose up -d` by hand once).
7. GitHub Actions CI/CD last — automate the deploy step already proven to work manually.

## 12. Cost/Cleanup Reminder
- Set an AWS Budget alert (~$5-10) before starting.
- Tear down EC2 instance (and any Elastic IP) same day once the demo is recorded/screenshotted.
- Keep code + this spec in GitHub permanently — that's the portfolio artifact, not the running infra.
