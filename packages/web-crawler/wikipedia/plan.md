The main objective here is to scrape wikipedia pages.

We are using a bot that aims to respect wikipedia's crawling requests.

We first need to give a name for our bot and add some contact information, we will link an email for contact.

We need to ensure we respect the websites robots.txt

we need to ensure we are respecting 5XX errors and 429.

We need to limit concurrent requests, add a general timer, have exponential backoff for 429 errors.


