-- SQL script to create linkedin_posts table for storing LinkedIn post details
-- Run this in your Supabase SQL Editor

-- Drop the foreign key constraint if it exists (in case table was created with it)
ALTER TABLE IF EXISTS public.linkedin_posts DROP CONSTRAINT IF EXISTS fk_user;

-- Create linkedin_posts table for storing LinkedIn post details (if it doesn't exist)
CREATE TABLE IF NOT EXISTS public.linkedin_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    post_urn TEXT NOT NULL,
    posted_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
    -- Note: No foreign key constraint (like linkedin_tokens table)
    -- User validation is handled through JWT tokens
    -- user_id is UUID type, post_urn is TEXT type
);

-- Create index on user_id for faster lookups
CREATE INDEX IF NOT EXISTS idx_linkedin_posts_user_id ON public.linkedin_posts(user_id);

-- Create index on posted_at for sorting and filtering
CREATE INDEX IF NOT EXISTS idx_linkedin_posts_posted_at ON public.linkedin_posts(posted_at DESC);

-- Create unique index on post_urn to prevent duplicate entries
CREATE UNIQUE INDEX IF NOT EXISTS idx_linkedin_posts_post_urn ON public.linkedin_posts(post_urn);

-- Add comments for documentation
COMMENT ON TABLE public.linkedin_posts IS 'Stores details of LinkedIn posts published through the platform';
COMMENT ON COLUMN public.linkedin_posts.id IS 'Primary key UUID';
COMMENT ON COLUMN public.linkedin_posts.user_id IS 'User ID (foreign key to auth.users table)';
COMMENT ON COLUMN public.linkedin_posts.post_urn IS 'LinkedIn post URN (e.g., urn:li:ugcPost:XXXX)';
COMMENT ON COLUMN public.linkedin_posts.posted_at IS 'Timestamp when the post was published to LinkedIn';
COMMENT ON COLUMN public.linkedin_posts.created_at IS 'Timestamp when the record was created in the database';

-- Enable Row Level Security
ALTER TABLE public.linkedin_posts ENABLE ROW LEVEL SECURITY;

-- Create policy to allow service role to manage all records
CREATE POLICY "Enable all access for service role" 
ON public.linkedin_posts 
FOR ALL 
TO service_role 
USING (true) 
WITH CHECK (true);
