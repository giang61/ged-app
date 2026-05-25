import os, runpy
os.environ["GED_FILE"] = "data/nguyen.ged"
runpy.run_path("main.py", run_name="__main__")