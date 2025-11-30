import sys
from app import SystemManager

def main():
    """Initializes and runs the SystemManager application."""
    # Create the application instance
    app = SystemManager()
    
    # Run the application
    exit_status = app.run(sys.argv)
    sys.exit(exit_status)

if __name__ == "__main__":
    main()