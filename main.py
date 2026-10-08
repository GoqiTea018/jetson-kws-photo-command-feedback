"""项目启动入口；运行逻辑集中在 voice_control 包中。"""

if __package__:
    from .voice_control.controller import main
else:
    from voice_control.controller import main


if __name__ == "__main__":
    main()
