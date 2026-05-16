try:
    from server.main import main
except ImportError:
    # Fallback when run as a script (e.g. inside a PyInstaller bundle).
    from main import main

if __name__ == "__main__":
    main()
