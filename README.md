🗞️ Extra extra! This is Finite News: the mindful, AI-assisted newspaper.   
  
No clickbait, ads, links, rabbit holes, opinions...no mercy! 😁

## Features
 - Gets headlines from trusted APIs and websites.
 - Uses rules ± an LLM (GPT) to filter out headlines that are opinion, clickbait, or ones you saw yesterday.
 - Forecasts your local weather.
 - Alerts you if your favorite NBA team is playing tonight.
 - Enlightens you with a quote or a joke.
  
## 🤔 Motivation
I happily pay for subscriptions to quality news sources and support essential journalism! But increasingly news websites and newsletters are filled with distractions, clickbait, pop-ups, and attention vampires. I made Finite News to deliver a personalized daily news email with less noise, no ads, no links, and with strict limits on the volume of content.
  
It collects the latest happenings, gets a local weather forecast, finds out if a favorite NBA team is playing today, and shares a joke or thought of day. The headlines are filtered by rules and, optionally, a large language model (GPT) to reduce junk and focus on learning what's happening in the world.

## 🥄 Installing
1. See "Designing your newspaper" below and create the necessary files.
2. Create an AWS account and a Sagemaker instance.
3. Make an S3 bucket dedicated to Finite News. If you haven't done it before, think of S3 as a Google Drive account.
    - Add the files you created in "Designing your newspaper"
4. Set up AWS Secrets Manager. Create a "secret", a collection of secrets, called `fn_secrets`.
    - Add a secret called `BUCKET_PATH`. It should include the URL to your S3 bucket.
    - If you don't name your secret "fn_secrets", or your region isn't "us-east-1", you'll want to edit the notebook to pass your values to the function `get_fn_secret()`
5. Create an account on sendgrid.com. This lets you send emails in the notebook (via an API).
    - Add your api key to your AWS Secrets Manager under `fn_secrets` as `SENDGRID_API_KEY`
6. (Optional) Create an API account on openai.com, to use GPT to filter headlines
    - Add your api key to your AWS Secrets Manager under `fn_secrets` as `OPENAI_API_KEY`
7. Test the notebook in Sagemaker. 
    - Select a Data Science 2.0 image with Python 3.8. Newer images and newer Python versions may work too! But the Data Science 1.0 image probably won't work.
    - Set Parameters at the top of the notebook to `DEV_MODE = True` etc so no email is sent. It will write the day's issues to a file in the notebook directory instead
8. Run the notebook as a scheduled job. This is easy!
    - Set Parameters at the top of the notebook to production mode, which at minimum requires `DEV_MODE = False`
    - Click the `Create a notebook job` icon in the menu bar.
    - Configure your scheduled job. Make sure the image is the same as what ran in your test run of the notebook (e.g. Data Science 2.0 and Python 3.8). See [Sagemaker notebook jobs](https://docs.aws.amazon.com/sagemaker/latest/dg/create-notebook-auto-run-studio.html) for more options.

## 💸 Costs
At the time of writing, with 4 subscribers getting an issue once a day, it costs me:
- AWS: 1-2 USD a month
- Sendgrid: Free
- Open AI api (optional): 0.5 USD a month with `gpt-4-1106-preview` model
  
With fewer subscribers, it's cheaper. With more, it's more. 😁  
  
### </> About the code base
This notebook is set up to run as a scheduled job in Sagemaker. I've found this to be a relatively easy and super cheap way to run a notebook every day.   
  
**All code is contained in the notebook.** Sagemaker uses Papermill to turn notebooks into jobs. One limitation is that Papermill jobs cannot import Python scripts from the local directory: it just airlifts the notebook into a scheduled job. So all code that runs in the job must be either in the notebook or imported from the SageMaker image. 
  
The notebook defines 3 concepts:
- **Subscription:** A customized version of Finite News that a single person receives daily. 
- **Issue:** One email delivered to one subscriber on one day.
- **Publication:** The internal processes and general paramaters that are shared by every issue and subscription.

## 📰 Designing your newspaper
🚨🚨 Comply with the Terms of Service of your sources and APIs.  
  
Add the following files to your S3 Bucket. See the `samples_files` folder for examples of each.
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

## ❤️ Contributing new features, filing bug reports, and asking questions
You're so sweet, thank you! These are extremely appreciated! The best way is to create a new Issue or Pull request in this repository.