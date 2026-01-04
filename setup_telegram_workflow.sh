#!/bin/bash

# Setup script for Weekly Corpus Report Telegram integration
# Helps configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID

set -e

echo "=================================================="
echo "Weekly Corpus Report - Telegram Setup"
echo "=================================================="
echo ""

# Check if .env file exists
ENV_FILE="/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/.env"

if [ -f "$ENV_FILE" ]; then
    echo "Found existing .env file at: $ENV_FILE"
    echo ""
    read -p "Do you want to update it with new Telegram credentials? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Skipping setup."
        exit 0
    fi
fi

echo ""
echo "SETUP INSTRUCTIONS:"
echo "===================="
echo ""
echo "Step 1: Create Telegram Bot"
echo "  1. Open Telegram app or web.telegram.org"
echo "  2. Search for @BotFather"
echo "  3. Send: /newbot"
echo "  4. Follow the prompts"
echo "  5. BotFather will give you a TOKEN like:"
echo "     123456789:ABCdefGHIJKlmnoPQRstuvWXYZabcdefGHI"
echo ""
echo "Step 2: Get Chat ID"
echo "  1. Add the bot to your group or personal chat"
echo "  2. Send a test message"
echo "  3. Run this command to see updates:"
echo "     curl https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates"
echo "  4. Look for 'chat':{'id': XXXX}"
echo ""
echo "=================================================="
echo ""

read -p "Enter TELEGRAM_BOT_TOKEN: " BOT_TOKEN
if [ -z "$BOT_TOKEN" ]; then
    echo "Error: Bot token cannot be empty"
    exit 1
fi

read -p "Enter TELEGRAM_CHAT_ID: " CHAT_ID
if [ -z "$CHAT_ID" ]; then
    echo "Error: Chat ID cannot be empty"
    exit 1
fi

# Validate token format
if ! [[ $BOT_TOKEN =~ ^[0-9]+:[A-Za-z0-9_-]+$ ]]; then
    echo "Warning: Token format looks invalid (expected: number:string)"
    echo "Proceeding anyway..."
fi

# Validate chat ID format
if ! [[ $CHAT_ID =~ ^-?[0-9]+$ ]]; then
    echo "Warning: Chat ID format looks invalid (expected: number, possibly negative)"
    echo "Proceeding anyway..."
fi

echo ""
echo "Testing Telegram credentials..."
echo ""

# Test the credentials
RESPONSE=$(curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getMe")

if echo "$RESPONSE" | grep -q "\"ok\":true"; then
    echo "✓ Bot token is valid!"
    BOT_NAME=$(echo "$RESPONSE" | grep -o '"first_name":"[^"]*"' | cut -d'"' -f4)
    BOT_USERNAME=$(echo "$RESPONSE" | grep -o '"username":"[^"]*"' | cut -d'"' -f4)
    echo "  Bot name: $BOT_NAME"
    echo "  Bot username: @$BOT_USERNAME"
else
    echo "✗ Bot token validation failed!"
    echo "  Response: $RESPONSE"
    echo ""
    echo "Please check your token and try again."
    exit 1
fi

echo ""
echo "Creating/updating .env file..."
echo ""

# Create or update .env file
if [ -f "$ENV_FILE" ]; then
    # Backup existing file
    cp "$ENV_FILE" "${ENV_FILE}.backup.$(date +%s)"
    echo "Backed up existing .env to: ${ENV_FILE}.backup.*"

    # Update existing file
    if grep -q "TELEGRAM_BOT_TOKEN" "$ENV_FILE"; then
        sed -i "s|TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=${BOT_TOKEN}|g" "$ENV_FILE"
    else
        echo "TELEGRAM_BOT_TOKEN=${BOT_TOKEN}" >> "$ENV_FILE"
    fi

    if grep -q "TELEGRAM_CHAT_ID" "$ENV_FILE"; then
        sed -i "s|TELEGRAM_CHAT_ID=.*|TELEGRAM_CHAT_ID=${CHAT_ID}|g" "$ENV_FILE"
    else
        echo "TELEGRAM_CHAT_ID=${CHAT_ID}" >> "$ENV_FILE"
    fi
else
    # Create new file
    cat > "$ENV_FILE" << EOF
# Telegram Configuration
TELEGRAM_BOT_TOKEN=${BOT_TOKEN}
TELEGRAM_CHAT_ID=${CHAT_ID}
EOF
fi

chmod 600 "$ENV_FILE"
echo "✓ Saved to: $ENV_FILE"

echo ""
echo "Next steps:"
echo "==========="
echo ""
echo "1. Import workflow to n8n:"
echo "   - Open n8n UI"
echo "   - Click '+' (New Workflow)"
echo "   - Click 'Import from file'"
echo "   - Select: weekly_corpus_report.json"
echo ""
echo "2. Configure n8n environment variables:"
echo "   - Go to Settings → Environment Variables"
echo "   - Add:"
echo "     TELEGRAM_BOT_TOKEN=${BOT_TOKEN}"
echo "     TELEGRAM_CHAT_ID=${CHAT_ID}"
echo ""
echo "3. Test the workflow:"
echo "   - Click 'Execute Workflow' in n8n"
echo "   - Or run: python3 test_corpus_report.py"
echo ""
echo "=================================================="
echo "✓ Setup complete!"
echo "=================================================="
