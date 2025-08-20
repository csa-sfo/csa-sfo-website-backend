-- Create payments table
CREATE TABLE IF NOT EXISTS public.payments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    stripe_payment_intent_id TEXT NOT NULL UNIQUE,
    stripe_customer_id TEXT,
    customer_email TEXT NOT NULL,
    customer_name TEXT,
    amount_total DECIMAL(10, 2) NOT NULL,
    currency TEXT NOT NULL,
    payment_status TEXT NOT NULL,
    product_id TEXT NOT NULL,
    product_name TEXT NOT NULL,
    amount_subtotal DECIMAL(10, 2) NOT NULL,
    payment_method TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    status TEXT NOT NULL
);

-- Create indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_payments_stripe_payment_intent_id ON public.payments(stripe_payment_intent_id);
CREATE INDEX IF NOT EXISTS idx_payments_customer_email ON public.payments(customer_email);
CREATE INDEX IF NOT EXISTS idx_payments_created_at ON public.payments(created_at);

-- Add comments for documentation
COMMENT ON TABLE public.payments IS 'Stores payment information from Stripe Checkout';
COMMENT ON COLUMN public.payments.stripe_payment_intent_id IS 'The Stripe PaymentIntent ID';
COMMENT ON COLUMN public.payments.stripe_customer_id IS 'The Stripe Customer ID if available';
COMMENT ON COLUMN public.payments.customer_email IS 'Email of the customer who made the payment';
COMMENT ON COLUMN public.payments.amount_total IS 'Total amount paid including taxes and fees';
COMMENT ON COLUMN public.payments.amount_subtotal IS 'Subtotal amount before taxes and fees';
COMMENT ON COLUMN public.payments.metadata IS 'Additional metadata associated with the payment';

-- Enable Row Level Security
ALTER TABLE public.payments ENABLE ROW LEVEL SECURITY;

-- Create policies for RLS
CREATE POLICY "Enable read access for authenticated users" 
ON public.payments 
FOR SELECT 
TO authenticated 
USING (true);

CREATE POLICY "Enable insert for authenticated users" 
ON public.payments 
FOR INSERT 
TO authenticated 
WITH CHECK (true);

-- Create a function to update the updated_at column
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create a trigger to update updated_at on row update
CREATE TRIGGER update_payments_updated_at
BEFORE UPDATE ON public.payments
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();
