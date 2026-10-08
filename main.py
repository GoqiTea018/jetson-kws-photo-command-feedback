"""Run the wake word and command listener."""

if __package__:
    from .live_photo import main
else:
    from live_photo import main


if __name__ == "__main__":
    main()
