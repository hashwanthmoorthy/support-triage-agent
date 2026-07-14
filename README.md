# Self-Healing Support Triage Agent

An LLM-powered customer-support ticket triage system. Incoming tickets are
classified by a LangGraph agent: **simple** tickets are resolved autonomously
via tool calls; **ambiguous** tickets pause for human approval before any action
is taken. Every run is traced in LangSmith. Deployed on a single AWS EC2
instance via Docker Compose.

## Architecture

```
Frontend (React + Vite, nginx)
  -> FastAPI backend
       -> LangGraph agent
            classify_ticket   (LLM: simple vs ambiguous)
            resolve_via_tools  (simple -> calls MCP tools)
            human_approval     (ambiguous -> interrupt() + checkpoint)
            apply_decision     (execute resolve / escalate)
       -> LangSmith (auto-traces every run via env vars)
  -> MCP tool server: ticket_lookup, knowledge_base_search (RAG), send_email
```

- **Human-in-the-loop:** ambiguous tickets call LangGraph's `interrupt()`, which
  checkpoints graph state and suspends the run. The frontend approve/reject hits
  `/resume`, which resumes the same thread.
- **RAG:** `knowledge_base_search` does semantic retrieval over local FAQ/policy
  docs using Chroma + a local `all-MiniLM-L6-v2` embedding model (no extra API
  key). The model and a pre-built index are baked into the backend image.

## Tech stack

Python 3.11 · FastAPI · LangChain · LangGraph · LangSmith (tracing) ·
Anthropic Claude · MCP (`mcp` + `langchain-mcp-adapters`) · Chroma ·
sentence-transformers · React + Vite · Docker Compose · GitHub Actions · AWS EC2.

Exact dependency versions are pinned in `backend/requirements.txt` and
`frontend/package.json`.

## Repo structure

```
backend/
  agent/          LangGraph nodes, state, graph, MCP client
  mcp_servers/    MCP tool server (ticket_lookup, knowledge_base_search, send_email)
  knowledge_base/ RAG docs + Chroma indexing/retrieval
  scripts/        local test + trace-verification scripts
  main.py         FastAPI app (/health, /triage, /resume)
  Dockerfile
frontend/         React + Vite app (nginx-served) + Dockerfile
docker-compose.yml
.github/workflows/deploy.yml
.env.example
```

## Environment variables

Copy `.env.example` to `.env` and fill in the values. **Never commit `.env`;
never paste real key values into chat.**

| Var | Purpose |
|-----|---------|
| `ANTHROPIC_API_KEY` | Claude API key (classification) |
| `LANGCHAIN_API_KEY` | LangSmith API key (tracing) |
| `LANGCHAIN_TRACING_V2` | `true` to enable tracing |
| `LANGCHAIN_PROJECT` | LangSmith project name (`support-triage-agent`) |
| `VITE_API_BASE` | Backend URL the browser calls (baked into the frontend at build) |
| `CORS_ORIGINS` | Comma-separated origins the backend allows |
| `MCP_SERVER_URL` | Where the backend reaches the MCP server (set by compose) |

## Run locally

### Docker (whole stack)

```bash
cp .env.example .env      # fill in ANTHROPIC_API_KEY (+ LangSmith key, optional)
docker compose up --build
# frontend: http://localhost:5173   backend: http://localhost:8000
```

### Without Docker (dev)

```bash
cd backend
python -m venv .venv && ./.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
python -m knowledge_base.index                    # build the RAG index once
python -m mcp_servers.server                       # terminal 1 (MCP server)
uvicorn main:app --port 8000                        # terminal 2 (backend)
cd ../frontend && npm install && npm run dev        # terminal 3 (frontend)
```

Test scripts (from `backend/`, with the MCP server running):
`scripts/test_mcp_tools.py`, `scripts/test_retriever.py`, `scripts/test_agent.py`,
`scripts/check_langsmith.py`.

## Deploy to AWS EC2

Single t3.small instance in a public subnet, Docker Compose, no ECR/Terraform.

### 1. Provision
- **Budget alert** first (Billing → Budgets, ~$10).
- **Key pair** (RSA `.pem`).
- **Security group** `triage-demo-sg` — inbound: `22` (your IP), `8000` (your IP),
  `5173` (your IP); outbound: all.
- **Launch:** Ubuntu 24.04 LTS (x86_64), **t3.small**, auto-assign public IP,
  **30 GiB gp3** EBS (the backend image is ~2.6 GB because of Torch), attach
  `triage-demo-sg`.

> ⚠️ **Verify the security group actually attached.** If a launch is retried or
> the AMI is changed mid-wizard, EC2 can silently fall back to a default
> `launch-wizard-*` group, leaving ports 8000/5173 closed — the site then looks
> "up" over SSH but is unreachable in the browser. Confirm under
> **Instance → Security**, and if wrong, reattach via
> **Actions → Security → Change security groups**.

### 2. Install Docker (on the instance)

```bash
curl -fsSL https://get.docker.com -o get-docker.sh && sudo sh get-docker.sh
sudo usermod -aG docker ubuntu && newgrp docker
docker compose version   # expect v2.x
```

### 3. Deploy

```bash
sudo apt-get update && sudo apt-get install -y git
cd /home/ubuntu && git clone https://github.com/hashwanthmoorthy/support-triage-agent.git app
cd app
cp .env.example .env
cat >> .env <<'EOF'
VITE_API_BASE=http://<PUBLIC_IP>:8000
CORS_ORIGINS=http://<PUBLIC_IP>:5173
EOF
nano .env                       # paste ANTHROPIC_API_KEY and LANGCHAIN_API_KEY
docker compose up -d --build    # first build takes several minutes
docker compose ps               # backend should be (healthy)
```

Open `http://<PUBLIC_IP>:5173`.

> `VITE_API_BASE` is baked into the frontend **at build time**, so it must be set
> before `docker compose up --build`. If triage calls fail from the browser while
> the UI loads, it's almost always a CORS/IP mismatch or a closed security-group
> port.

## CI/CD

`.github/workflows/deploy.yml` deploys on push to `main`: it SSHes into the
instance, writes `.env` from GitHub secrets, `git pull`s, and rebuilds the stack.

Required GitHub repo **secrets**: `EC2_HOST`, `EC2_SSH_KEY` (the `.pem`
contents), `ANTHROPIC_API_KEY`, `LANGCHAIN_API_KEY`.

## Cost / cleanup

This is a demo. Set a budget alert, and **tear down the EC2 instance (and any
Elastic IP) the same day** once recorded. The permanent portfolio artifact is
this repo, not the running infrastructure.
