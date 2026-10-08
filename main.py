"""项目启动入口；运行逻辑集中在 voice_control 包中。"""

# 作为 photo_test.main 导入时用相对路径；直接运行 main.py 时用顶层包名。
if __package__:
    from .voice_control.controller import main
else:
    from voice_control.controller import main


if __name__ == "__main__":
    main()
