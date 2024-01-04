🗞️ Extra extra! This is Finite News: the mindful, AI-assisted newspaper.   
  
## 🤔 Motivation
I happily pay for subscriptions to quality news sources and support essential journalism! But increasingly news websites and newsletters are filled with clickbait, pop-ups, and attention vampires.
  
I made Finite News to deliver a lean, personalized daily news email. Its goal is to reduce distractions and focus on what's happening in the world.
  
## 👀 Features
 - Gets headlines from your trusted APIs and websites.
 - Enforces strict limits on the volume of news, and leaves out ads and links.
 - Applies an LLM and rules to consolidate headlines that are about the same topic and remove opinions, clickbait, and news you saw yesterday.
 - Forecasts your local weather.
 - Updates you on stock prices.
 - Optionally
     - Alerts you if your favorite NBA team plays tonight.
     - Lists upcoming events of interest.
     - Shares a joke or quote.
  
## 📰 Make your own newspaper
### How it works
Finite News is set up to run as a scheduled job in AWS Sagemaker.
  
### Concepts to know
- **Publication:** The general processes that are shared by every issue and subscription.
- **Subscription:** The customizations that personalize Finite News for a single person (subscriber).
- **Issue:** One email delivered to one subscriber.
  
### Installing
1. First, you need to create data files that configure everything about Finite News. See "Designing your newspaper" below.
2. Create an AWS account and a [Sagemaker domain](https://aws.amazon.com/pm/sagemaker).
3. Clone this repo as a directory in your Sagemaker environment.
4. Make a new [AWS S3 bucket](https://aws.amazon.com/s3/).
5. Add to S3 the files you created in "Designing your newspaper"
6. Set up [AWS Secrets Manager](https://aws.amazon.com/secrets-manager/). Create a "secret" (really it's a collection of secrets) called `fn_secrets`.
    - Add a new item to `fn_secrets` called `BUCKET_PATH` with the value of the URL to your S3 bucket.
    - 💡 If you don't name your secret "fn_secrets", or your region isn't "us-east-1", you'll want to edit the notebook to pass your values to the function `get_fn_secret()`
7. Create an account on sendgrid.com. This lets you send emails in the notebook (via an API).
    - Add your api key to your AWS Secrets Manager under `fn_secrets` as `SENDGRID_API_KEY`
8. (Optional) Create an API account on openai.com, to use GPT to filter headlines
    - Add your api key to your AWS Secrets Manager under `fn_secrets` as `OPENAI_API_KEY`
9. Test the notebook `finite_news.ipynb` in Sagemaker.
    - Select a Data Science 2.0 image with Python 3.8. Newer images and newer Python versions may work too! But the "Data Science" (1.0) image may not.
    - In the Parameters cell, set `DEV_MODE = True` etc so no email is sent. It will write the day's issues to a file in the notebook directory instead.
    - Inspect the file.
10. Run the notebook as a [scheduled job](https://docs.aws.amazon.com/sagemaker/latest/dg/create-notebook-auto-run-studio.html). This is easy!
    - Set Parameters at the top of the notebook to production mode, which at minimum requires `DEV_MODE = False`
    - Click the `Create a notebook job` icon in the menu bar.
    - Set the schedule for how often it should run. If you want to publish daily issues, select Day and a time in GMT.
    - 💡 Make sure it uses the same image (Data Science 2.0 etc) that worked in your test.
  
### Designing your newspaper
🚨🚨 Comply with the Terms of Service of your sources and APIs.  
  
Create the following files. See the `samples_files` folder for examples. Later, your files will go in your AWS S3 Bucket.
- `publication_config.yml`: General choices for how to run Finite News
    - This includes setting up individual news sources. See the sample `publication_config.yml` for instructions.
    - If you need an API key to access a particular news source, add `api_key_name: {NAME OF YOUR API KEY}` under that source in `publication_config.yml`. Then add a new secret in your AWS Secrets Manager, under your `fn_secrets`, that is called {NAME OF YOUR API KEY}, like in publication_config.yml, and set the secret value to your api key.
    - To disable GPT, delete the `gpt` section in `publication_config.yml`.
- `config_*.yml`: Configuration for each subscription (each daily email). 
    - To add a new subscriber, create a new `config_their_name.yml` file and upload to the S3 bucket. 
    - Finite News creates the list of subscribers by looking for all YML files in the bucket that begin with `config_`.
- `template.htm`: The layout for the email. The parts in `[[ ]]` are populated by the code at runtime.
- `substance_rules.yml`: Policies for identifying "low substance" headlines to always drop. You can add rules to remove headlines on topics you don't want to hear about or recurring noise. 
- `thoughts_of_the_day.yml`: (optional) Shared list of jokes and quotes sampled for Thought of the Day. To enable, in `config_*.yml` file(s) set `add_shared_thoughts=True`.
  
### Costs
💸 At the time of writing, publishing FiniteNews to 5 daily subscribers costs around 2 USD a month.
- AWS SageMaker, S3: $1 per month
- OpenAI API (optional): $1 per month with `gpt-4-1106-preview` model
- Sendgrid: Free at this volume of emails
  
## ❤️ Bugs, questions, and contributions
You're awesome, thank you! The best way is to create a new Issue or Pull Request.