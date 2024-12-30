## Welcome to Finite News!
## This entry point orchestrates all the tasks to create and email issues of Finite News.

from tasks.publishing import run_finite_news

if __name__ == "__main__":
    run_finite_news(dev_mode=False)
