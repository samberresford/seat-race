# Seat Racing & Crew Selection App

A tool I built for the University of Exeter Boat Club (about 300 members) to make crew selection fairer and more evidence-based. It ranks athletes, plans seat-racing sessions, records the results, and won't call a seat on indirect evidence alone.

![Seat racing plan](screenshot.png)

## What it does

- **Calculator** – works out who won a seat race from the two margins, and saves the result.
- **Squad** – ranks athletes by erg power adjusted for technique, shows who is in, borderline or out for a given boat, and compares the coach's ranking with the model's.
- **Seat Racing** – picks the athletes near the selection cut, builds two even crews, and plans sessions of pieces with one swap each, with boat diagrams.
- **Results** – every head-to-head, average margins, and a check for any two athletes: a clear direct result, too close to call, an indirect estimate (clearly flagged), or no link at all.

## How it works

- **Erg power:** a 2k time is converted to watts with the Concept2 formula, `watts = 2.80 / (split / 500)³`, so differences at the fast end are weighted fairly.
- **Technique:** poor technique wastes power, so each athlete keeps a share of their erg watts based on a 0–100 tech score. A slider sets how much tech matters.
- **Seat race maths:** swapping two athletes changes both boats, so the athlete difference is half the change in margin between the two pieces.
- **Ratings:** each race is one equation (rating A − rating B = margin per 500 m). Least squares finds the ratings that best fit every race, which lets the app estimate athletes who never raced each other – but it labels those as indirect.

## Run it yourself

```
pip install -r requirements.txt
streamlit run app.py
```

It runs on `sample_squad.csv`, a made-up squad. The club's real data (`squad.csv`, `seat_races.csv`) is kept off GitHub.

## What I learned

- Turning a coaching problem into rules a program can follow, and deciding where the program should refuse to decide.
- Python, pandas and Streamlit from close to zero, plus cleaning two seasons of messy erg data.
- Building something people actually use, and changing it when the coach's view and the numbers disagreed.

Built with Python, pandas, NumPy and Streamlit. I used Claude (AI) as a tutor and pair-programmer while learning.
