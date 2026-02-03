-- Create conversations table
CREATE TABLE IF NOT EXISTS conversation_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    session_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Create conversation turns table
CREATE TABLE IF NOT EXISTS conversation_turns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES conversation_sessions(id) ON DELETE CASCADE,
    turn_number INT NOT NULL,
    role VARCHAR(50) NOT NULL, -- 'user' or 'assistant'
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create agent responses table
CREATE TABLE IF NOT EXISTS agent_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    turn_id UUID NOT NULL REFERENCES conversation_turns(id) ON DELETE CASCADE,
    agent_name VARCHAR(100) NOT NULL,
    tools_used TEXT[], -- array of tool names
    result TEXT NOT NULL,
    duration_ms INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_sessions_user_id ON conversation_sessions(user_id);
CREATE INDEX idx_turns_session_id ON conversation_turns(session_id);
CREATE INDEX idx_turns_created_at ON conversation_turns(created_at);
CREATE INDEX idx_responses_turn_id ON agent_responses(turn_id);
CREATE INDEX idx_responses_agent ON agent_responses(agent_name);