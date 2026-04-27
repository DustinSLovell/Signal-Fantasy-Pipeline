# Career Lessons Database
# Last updated: April 24, 2026

All career transition lessons, interview
answers, and technical concepts have been
consolidated into the HTML database file:

File:     career_lessons_database.html
Location: C:\Users\dusti\fantasy-baseball\
Concepts: 88 (4 sessions merged)
Format:   Open in any browser, fully
          searchable by category

Categories covered:
- ML/Modeling (21 concepts)
- Engineering (19 concepts)
- Product (12 concepts)
- Business (9 concepts)
- Communication (7 concepts)
- Career & Positioning (11 concepts)
- Infrastructure & AI Systems (9 concepts)

To add a new lesson, append to the bottom
of career_lessons_database.html in the
LESSONS array using this format:
{
  concept: "Concept Name",
  tags: ["category"],
  session: "Date",
  accent: "#colorhex",
  lesson: "The career insight",
  interview: "Answer using this project"
}

---
NEW LESSONS THIS SESSION (April 24, 2026):

CONCEPT: Metric Complementarity
LESSON: Understanding what each metric
measures AND what it doesn't is more
valuable than knowing the metric itself.
FIP and xERA aren't redundant — FIP
measures strike zone command, xERA measures
contact quality. A pitcher with good FIP
and bad xERA is a sell signal precisely
because FIP can't see what xERA can.
INTERVIEW ANSWER: "I use complementary
metrics rather than redundant ones. FIP
tells you about a pitcher's command of
the strike zone. xERA tells you about
contact quality allowed. Vásquez had good
FIP (2.50) and terrible xERA (4.29) —
the gap is the signal. A black-box model
can't explain that. Mine can."
SESSION: April 24, 2026

CONCEPT: Construct Validity
LESSON: Does your metric actually measure
what you think it measures? TRM was
designed to measure projection confidence
but functionally measured career longevity
— correlated but not the same thing.
A player can have high projection
confidence after 600 PA if metrics
are stable and consistent.
INTERVIEW ANSWER: "I audited the track
record multiplier and found it had a
60-point range that functionally acted
as a career longevity bonus rather than
a projection confidence discount. Young
quality players were systematically
undervalued 25-30% vs aging veterans.
I narrowed the range from 0.40-1.00
to 0.75-1.00."
SESSION: April 24, 2026

CONCEPT: Ablation Testing a Value Model
LESSON: Ablation testing a value/ranking
model is different from ablating a
classification model. Instead of measuring
accuracy delta, you measure ranking
COHERENCE — does the model still pass
domain expertise validation when you
remove each component?
INTERVIEW ANSWER: "I ablation tested
the value model by removing one component
at a time and asking: does the ranking
still make intuitive sense? Removing the
AVG penalty caused Sanchez to jump from
rank 21 to rank 4 among catchers — that
proved the penalty was load-bearing and
necessary. Every component had to prove
it earned its place."
SESSION: April 24, 2026

CONCEPT: Invariant Testing
LESSON: Every model needs a set of
outputs so unambiguous that if the model
disagrees, you know something broke.
These invariants catch subtle bugs that
pass statistical validation but fail
domain expertise tests.
INTERVIEW ANSWER: "I maintain permanent
invariant test cases — players whose
correct ranking is unambiguous. Yordan
Alvarez should always be top 20 overall.
Gary Sanchez should always be bottom half
of catchers. If a model update violates
those invariants, the update is wrong —
not the invariant. This caught the
Sanchez bug before it went public."
SESSION: April 24, 2026

CONCEPT: Asymmetric Category Damage
LESSON: In roto scoring, categories
aren't symmetric. A .188 AVG doesn't
just underperform — it actively damages
a roster in a way that .240 doesn't.
Most valuation models treat all
below-average AVG as equally weighted.
INTERVIEW ANSWER: "I identified that
my player valuation model treated all
below-average AVG performances as
equally weighted when in roto scoring
they're not. A .188 AVG is a roster
poison that makes every other hitter
look worse in the standings. I built
a categorical AVG liability penalty
that fires below .220."
SESSION: April 24, 2026

CONCEPT: Content Inventory Management
LESSON: Your best signals are a scarce
resource that needs to be rationed
across the publishing calendar. Most
first-time publishers burn their best
material in week one. Knowing when to
hold a signal for maximum impact is
the same instinct that makes a good
VP Analytics.
INTERVIEW ANSWER: "I treat high-value
analytical signals the same way I'd
treat insights in a board presentation
— timing matters as much as accuracy.
I deliberately held Seager as a Week 2
lead story rather than burning him in
a mid-week post, and used the mid-week
slot for community service content
instead. The insight is more valuable
when timed correctly."
SESSION: April 24, 2026
