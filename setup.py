#!/usr/bin/env python
"""
BONASO Data Portal - Django Backend Setup Script
Run this after installing requirements to set up the database and create a superuser.
"""

import os
import sys
import django
from pathlib import Path

def main():
    # Set up Django settings
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
    
    # Add the project directory to the path
    project_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(project_dir))
    
    django.setup()
    
    from django.core.management import execute_from_command_line
    from django.contrib.auth import get_user_model
    
    print("=" * 50)
    print("BONASO Data Portal - Setup")
    print("=" * 50)
    
    # Run migrations
    print("\n[1/3] Running database migrations...")
    execute_from_command_line(['manage.py', 'migrate'])
    
    # Create superuser if doesn't exist
    print("\n[2/3] Checking for superuser...")
    User = get_user_model()
    if not User.objects.filter(is_superuser=True).exists():
        print("Creating superuser...")
        username = input("Enter superuser username (default: admin): ").strip() or "admin"
        email = input("Enter superuser email: ").strip()
        
        from django.contrib.auth.hashers import make_password
        import getpass
        password = getpass.getpass("Enter superuser password: ")
        
        User.objects.create(
            username=username,
            email=email,
            password=make_password(password),
            is_superuser=True,
            is_staff=True,
            is_active=True,
            role='admin'
        )
        print(f"Superuser '{username}' created successfully!")
    else:
        print("Superuser already exists.")
    
    # Create sample data
    print("\n[3/3] Setup complete!")
    print("\n" + "=" * 50)
    print("To start the development server, run:")
    print("  python manage.py runserver")
    print("\nThe API will be available at:")
    print("  http://localhost:8000/api/")
    print("\nAdmin panel:")
    print("  http://localhost:8000/admin/")
    print("=" * 50)


if __name__ == '__main__':
    main()
