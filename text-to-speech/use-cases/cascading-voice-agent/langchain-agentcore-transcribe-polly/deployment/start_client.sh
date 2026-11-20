#!/bin/bash
#
# Launch the browser client for the deployed cascading voice agent.
#
# Reads the agent ARN + region from setup_config.json (written by deploy.py),
# generates a SigV4 presigned WebSocket URL, and opens the HTML client.
#
# Usage:
#   ./start_client.sh
#
set -e

GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

# deployment/ lives inside the sample folder; resolve both.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SAMPLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_FILE="$SAMPLE_DIR/setup_config.json"

echo -e "${BLUE}🚀 Starting cascading voice agent client${NC}\n"

# Auto-fetch AWS credentials from EC2 IMDS if not already set (workshop convenience).
if [ -z "$AWS_ACCESS_KEY_ID" ]; then
    echo -e "${YELLOW}🔑 Fetching AWS credentials from instance metadata...${NC}"
    TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" 2>/dev/null || true)
    if [ -n "$TOKEN" ]; then
        ROLE_NAME=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/iam/security-credentials/ 2>/dev/null || true)
        if [ -n "$ROLE_NAME" ]; then
            CREDS=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" "http://169.254.169.254/latest/meta-data/iam/security-credentials/$ROLE_NAME" 2>/dev/null)
            export AWS_ACCESS_KEY_ID=$(echo "$CREDS" | python3 -c "import sys,json; print(json.load(sys.stdin)['AccessKeyId'])" 2>/dev/null)
            export AWS_SECRET_ACCESS_KEY=$(echo "$CREDS" | python3 -c "import sys,json; print(json.load(sys.stdin)['SecretAccessKey'])" 2>/dev/null)
            export AWS_SESSION_TOKEN=$(echo "$CREDS" | python3 -c "import sys,json; print(json.load(sys.stdin)['Token'])" 2>/dev/null)
            echo -e "${GREEN}   ✅ Credentials loaded from role: $ROLE_NAME${NC}"
        fi
    else
        echo -e "${YELLOW}   ⚠️  IMDS not available. Using existing environment / profile credentials.${NC}"
    fi
else
    echo -e "${GREEN}🔑 Using existing AWS credentials from environment${NC}"
fi
echo ""

if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}❌ Configuration file not found: $CONFIG_FILE${NC}"
    echo "   Run the deployment first:  python deployment/deploy.py"
    exit 1
fi

if ! command -v jq &> /dev/null; then
    echo -e "${RED}❌ jq is not installed (needed to parse setup_config.json)${NC}"
    exit 1
fi

AGENT_ARN=$(jq -r '.agent_arn' "$CONFIG_FILE")
AWS_REGION=$(jq -r '.aws_region' "$CONFIG_FILE")

if [ -z "$AGENT_ARN" ] || [ "$AGENT_ARN" = "null" ]; then
    echo -e "${RED}❌ Agent ARN not found in configuration${NC}"; exit 1
fi
if [ -z "$AWS_REGION" ] || [ "$AWS_REGION" = "null" ]; then AWS_REGION="us-east-1"; fi
export AWS_REGION

echo -e "${GREEN}✅ Configuration loaded${NC}"
echo "   Agent ARN:  $AGENT_ARN"
echo "   AWS Region: $AWS_REGION"
echo ""

# Create a local virtual environment for the client if one doesn't exist.
VENV_DIR="$SAMPLE_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}Creating virtual environment for the client...${NC}"
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    pip install -q -r "$SAMPLE_DIR/client/requirements.txt"
else
    source "$VENV_DIR/bin/activate"
fi

echo -e "${GREEN}🎉 Launching client (browser will open automatically)${NC}\n"
python "$SAMPLE_DIR/client/client.py" --runtime-arn "$AGENT_ARN"
