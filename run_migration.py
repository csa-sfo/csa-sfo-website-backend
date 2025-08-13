import os
import psycopg2
from urllib.parse import urlparse
from dotenv import load_dotenv

def parse_db_url(db_url):
    """Parse Supabase database URL into connection parameters"""
    result = urlparse(db_url)
    return {
        'dbname': result.path[1:],  # Remove leading '/'
        'user': result.username,
        'password': result.password,
        'host': result.hostname,
        'port': result.port or 5432
    }

def run_migration():
    """Run database migrations"""
    # Load environment variables
    load_dotenv()
    
    # # Get Supabase connection details from environment variables
    # supabase_url = os.getenv('SUPABASEURLIND')
    # db_host = supabase_url.replace('https://', '').replace('.supabase.co', '')
    
    # # Get the database password from environment variables
    # db_password = os.getenv('DB_PASSWORD')
    # if not db_password or db_password == 'your_supabase_password_here':
    #     print("\nERROR: Please set your database password in the .env file")
    #     print("Replace 'your_supabase_password_here' with your actual database password")
    #     exit(1)
        
    # Construct the database URL
    db_url = os.getenv('SUPABASEURLIND')
    
    print(f"Connecting to database at: {db_url}")
    
    # Parse the database URL
    db_params = parse_db_url(db_url)
    
    conn = None
    try:
        print("Connecting to the database...")
        conn = psycopg2.connect(**db_params)
        conn.autocommit = True  # Enable autocommit for DDL statements
        cursor = conn.cursor()
        
        # Enable the uuid-ossp extension if not already enabled
        print("Enabling uuid-ossp extension...")
        cursor.execute("""
        CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
        """)
        
        # Read the migration file
        migration_file = os.path.join(os.path.dirname(__file__), 'migrations', '20240808000000_create_payments_table.sql')
        print(f"Reading migration file: {migration_file}")
        
        with open(migration_file, 'r', encoding='utf-8') as f:
            sql_script = f.read()
        
        # Execute the entire script as a single statement
        # This handles function definitions and other complex SQL that might contain semicolons
        try:
            print("Executing migration script...")
            cursor.execute(sql_script)
        except Exception as e:
            print(f"Error executing migration: {e}")
            # Print the specific part of the SQL that caused the error
            error_position = getattr(e, 'cursor', None) and getattr(e.cursor, 'pos', None)
            if error_position is not None:
                context = 200  # number of characters to show before and after the error
                start = max(0, error_position - context)
                end = min(len(sql_script), error_position + context)
                print("Error context:")
                print("-" * 40)
                print(sql_script[start:end])
                print("^" * 40)
            raise
        
        print("\nMigration completed successfully!")
        
    except Exception as e:
        print(f"\nError running migration: {str(e)}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()
    
    return True

if __name__ == "__main__":
    print("Starting database migration...")
    success = run_migration()
    if not success:
        print("\nMigration failed. Please check the error messages above.")
        exit(1)
    print("\nMigration completed successfully. You can now process payments.")
