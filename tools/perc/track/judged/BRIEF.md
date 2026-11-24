# Labelling by eye - the brief every labeller of PLAN-tracker step 1 follows

You look at sheet images (PNG) of MapleStory footage and write one judgment per case. The reference is your look:
judge only by what the pictures show. Do NOT read or run anything else of the project for answers: not
cases.json, b_cases.json, any other *.jsonl in tools/perc/track/judged/, the prototypes' outputs or code. You may
make enlarged crops of a sheet to look closer: `C:\Users\Yoav\dev\maple-work\.venv\Scripts\python.exe` with cv2
(headless: write a PNG into your own scratch folder, then Read it). Never write anywhere but your output file
(and your scratch folder).

The game: MapleStory (2D side view). Our character is a warrior with a polearm, name tag "JenkinsJob" (helmet,
dark armour). Other characters carry their own name tags; pets carry small name tags too ("Brown Puppy", "White
Bunny", "Snail" ...). Mobs: Bubbling (blue drop, Kerning subway "Line 1"), Horny Mushroom (blue-spotted cap), Zombie
Mushroom (grey cap, talisman), Stirge (flying bat), Evil Eye (yellow one-eyed lizard), Jr. Boogie (small ghost),
Drake (dragon), Slime (green jelly), Green Mushroom. A hit mob flinches (hit pose), a dying mob plays its death
animation and fades. Damage numbers are coloured digits over mobs; skill effects are bright arcs / sparks.
Purple padding on a crop = outside the game frame.

Output: one JSON object per line, `{"case": K, ...fields}` - K = the case number printed in the sheet's header.
Write every case of your range, in order, nothing else in the file. Use "?" whenever you cannot tell: a wrong
guess is worse than "?". When done, reply with: the number of cases written, how many "?" you gave, and anything
odd you saw on the sheets (a sheet that is broken, a question that did not fit a case) - short.
