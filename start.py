#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vanna.AI Unified Application Starter (Factory Pattern)
----------------------------------------------------
This is the recommended script to run the application using the app factory pattern.

It performs the following actions:
1. Sets up the correct module import paths.
2. Imports the app factory `create_app` from the 'src' package.
3. Creates the application instance and runs the development server.
"""

import sys
import os
import traceback
import logging

def setup_logging():
    """Configures global logging"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    
    logging.basicConfig(
        level=logging.DEBUG,
        format=log_format,
        filename='debug.log',
        filemode='w',
        encoding='utf-8'
    )
    
    logging.getLogger('werkzeug').setLevel(logging.INFO)
    logging.getLogger('httpx').setLevel(logging.INFO)

def main():
    """
    Configures the environment and starts the application.
    """
    project_root = os.path.dirname(os.path.abspath(__file__))
    
    # Add the project root to sys.path to allow imports from 'src'
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    print("=" * 60)
    print("Vanna.AI Application Starter (Factory Pattern)")
    print(f"Project Root: {project_root}")
    print("=" * 60)

    try:
        # Import the factory function after setting up the path
        from src.app import create_app

        print("--> Imported create_app factory from src.app")
        
        # Create the application instance
        app = create_app()
        print("--> Flask application instance created successfully.")

        # Configure logging for the application
        # You can customize this further if needed
        setup_logging()
        app.logger.info("Application logging configured.")
        
        print("--> Starting Flask development server on http://0.0.0.0:9091...")
        # In a production environment, you would use a WSGI server like Gunicorn or uWSGI
        app.run(host='0.0.0.0', port=9091, debug=True, use_reloader=False)

    except ImportError as e:
        print("\n[FATAL ERROR] Could not import the application factory.")
        print(f"Error: {e}")
        print("\nPlease ensure 'src/app.py' contains a 'create_app' function.")
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n[FATAL ERROR] An unexpected error occurred.")
        print(f"Error: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 