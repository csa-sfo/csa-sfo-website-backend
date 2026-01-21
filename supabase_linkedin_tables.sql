-- SQL script to create tables for LinkedIn OAuth integration
-- Run this in your Supabase SQL Editor for project: ganqwjbdeivsmyekvojt

-- Create oauth_states table for LinkedIn OAuth state management
CREATE TABLE IF NOT EXISTS public.oauth_states (
    state TEXT PRIMARY KEY,
    user_id UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

-- Create index on user_id for faster lookups
CREATE INDEX IF NOT EXISTS idx_oauth_states_user_id ON public.oauth_states(user_id);

-- Create index on expires_at for cleanup operations
CREATE INDEX IF NOT EXISTS idx_oauth_states_expires_at ON public.oauth_states(expires_at);

-- Add comments for documentation
COMMENT ON TABLE public.oauth_states IS 'Stores OAuth state parameters for LinkedIn OAuth flow';
COMMENT ON COLUMN public.oauth_states.state IS 'Unique state parameter for OAuth CSRF protection';
COMMENT ON COLUMN public.oauth_states.user_id IS 'User ID associated with the OAuth state';
COMMENT ON COLUMN public.oauth_states.expires_at IS 'Expiration timestamp for the state parameter';

-- Enable Row Level Security
ALTER TABLE public.oauth_states ENABLE ROW LEVEL SECURITY;

-- Create policy to allow service role to manage all records
CREATE POLICY "Enable all access for service role" 
ON public.oauth_states 
FOR ALL 
TO service_role 
USING (true) 
WITH CHECK (true);

-- Create linkedin_tokens table for storing LinkedIn OAuth tokens
CREATE TABLE IF NOT EXISTS public.linkedin_tokens (
    user_id UUID PRIMARY KEY,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    expires_at NUMERIC NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index on expires_at for token expiration checks
CREATE INDEX IF NOT EXISTS idx_linkedin_tokens_expires_at ON public.linkedin_tokens(expires_at);

-- Add comments for documentation
COMMENT ON TABLE public.linkedin_tokens IS 'Stores LinkedIn OAuth access and refresh tokens for users';
COMMENT ON COLUMN public.linkedin_tokens.user_id IS 'User ID (foreign key to users table)';
COMMENT ON COLUMN public.linkedin_tokens.access_token IS 'LinkedIn OAuth access token';
COMMENT ON COLUMN public.linkedin_tokens.refresh_token IS 'LinkedIn OAuth refresh token (optional)';
COMMENT ON COLUMN public.linkedin_tokens.expires_at IS 'Token expiration timestamp (Unix timestamp)';
COMMENT ON COLUMN public.linkedin_tokens.created_at IS 'When the token record was created';
COMMENT ON COLUMN public.linkedin_tokens.updated_at IS 'When the token record was last updated';

-- Enable Row Level Security
ALTER TABLE public.linkedin_tokens ENABLE ROW LEVEL SECURITY;

-- Create policy to allow service role to manage all records
CREATE POLICY "Enable all access for service role" 
ON public.linkedin_tokens 
FOR ALL 
TO service_role 
USING (true) 
WITH CHECK (true);
