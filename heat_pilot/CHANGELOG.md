# Changelog – Heat Pilot

Newest first. Each version lists what changed since the one before.

## 0.30.2 – 2026-11-23

- A thermostat that falls back to its old setpoint soon after Heat Pilot set it (an Aqara E1 restarting on weak batteries) is no longer taken as turned by hand - so its old value isn't copied to the room's other thermostats or learned as the room's comfort. It is sent again next round

## 0.30.1 – 2026-11-21

- The ventilation no longer looks for an old AppDaemon app's limits at start - it uses its own and what you set

## 0.30.0 – 2026-11-20

- Lost room sensor: after 15 minutes the thermostat is put back on its own sensor, so it never regulates on an old number
- Floor heating in safe mode while the room sensor is lost: it holds the room's setback temperature until the sensor is back (the thermostat isn't in the room)
- New warning "Room sensor not responding" after 30 minutes - in the app and to the chosen phones; the room shows "Safe mode"
- Everything returns to normal by itself when the sensor is back

## 0.29.6 – 2026-11-20

- Home Assistant now downloads the ready-made app (amd64/aarch64) instead of building it on your machine: faster updates and no build leftovers on the disk

## 0.29.5 – 2026-11-19

- Rain looks like rain (blue slanted drops), snow is visible, no sun or moon in bad weather, a bare tree in snow

## 0.29.4 – 2026-11-17

- Sonoff TRVZB: recognised by its Zigbee2MQTT name, room temperature sent with the newer part names

## 0.29.3 – 2026-11-16

- Floor heating: a valve that can be turned off is turned off when the room is over its target (a W600 kept ~17 % open at 2 degrees less), and back on at the target
- Store and update links open right inside Home Assistant
- Open menus and the place on the page stay after a change

## 0.29.2 – 2026-11-15

- Setup: maker and model from another device of the same integration when missing
- Setup names - people found also with æ/ø/å, rooms stay

## 0.29.1 – 2026-11-14

- Setup names nearly whole - only people (also Lilly's), rooms, zones, home and device names swapped

## 0.29.0 – 2026-11-14

- How it is set up goes with the daily question (names cleaned), Share my setup for the full names

## 0.28.0 – 2026-11-14

- Hot water - the tank heated when power is cheap

## 0.27.0 – 2026-11-14

- Update card (new version, your error fixed) and the version in the daily question

## 0.26.0 – 2026-11-14

- L-shaped rooms (parts), sloped inner walls, a garden with season plants and soft shadows

## 0.25.1 – 2026-11-14

- The two outer front walls are low, solid walls with a white top

## 0.25.0 – 2026-11-14

- A nicer house (walls, windows, wood floors, light) and Fit the plan - drag the rooms to match your own floor plan

## 0.24.0 – 2026-11-14

- Suggestions of the other apps (fits your home, from the same developer)

## 0.23.0 – 2026-11-14

- New look in the family of Energy Pilot - the house in 3D with glowing rooms, seasons and holidays, thermostat dials, a floating menu
- Help under Settings
- Warm-on-time counted right

## 0.22.2 – 2026-11-14

- Errors from Home Assistant restarting or the network (502, timeout, no connection) are not reported
- The real version in errors (was 'dev')

## 0.22.1 – 2026-11-14

- The Send button shows on the add-on's own page (colours without Home Assistant's theme)

## 0.22.0 – 2026-11-14

- Help - get help, answers from the developer, errors sent anonymously

## 0.21.0 – 2026-11-12

- The ventilation card - a glowing ring with the step, and the heat exchanger as a live picture: cold air in turning warm, used air out turning cool

## 0.20.2 – 2026-11-12

- The ventilation card takes the height it needs on a sections dashboard

## 0.20.1 – 2026-11-12

- The ventilation card a little bigger - a live heat exchanger line, a soft glow and air in the state's colour

## 0.20.0 – 2026-11-12

- Heat Pilot can run the ventilation (shadow first): the unit in manual then the step, back to automatic on hand-back
- The unit's own modes and turns by hand are left alone
- Pre-cooling before a warm day
- The card's buttons (boost, away, auto) through heat_pilot.ventilation

## 0.19.1 – 2026-11-12

- Ventilation card in shadow says what Heat Pilot would do beside the unit's real step

## 0.19.0 – 2026-11-12

- Ventilation card - one slim line: the step the unit runs on, why, and what matters now
- Folds open on a tap

## 0.18.4 – 2026-11-12

- Floor heating with a slow valve - a room more than half a degree over is asked 2° less until it's back at its target, so the valve closes

## 0.18.3 – 2026-11-12

- No flashing on refresh - the page is left alone when nothing changed, and the painted house is kept when nothing in it changed

## 0.18.2 – 2026-11-12

- CO2 goes straight to full air at the limit (1200, or what AppDaemon learned) - a middle level hardly lowers it
- Low when it's cold outside and the air is fine

## 0.18.1 – 2026-11-12

- No blinking - the air colours stand still, the deciding room breathes slowly, and the animations keep their place when the page refreshes

## 0.18.0 – 2026-11-12

- Ventilation in shadow - each room counts for what the air can do there (vents in/out), shower, damp, dust, CO2, night, dew point
- Agreement with what runs the unit
- The unit in the attic, room air colours and the deciding room in the house

## 0.17.0 – 2026-11-12

- Painted house - real weather, time of day, seasons and Danish holidays

## 0.16.0 – 2026-11-12

- Watchdog - thermostats that don't obey
- Restarts Zigbee2MQTT, ZHA or Matter when turned on

## 0.15.4 – 2026-11-12

- A room can be set to learn nothing (own hours and comfort)

## 0.15.3 – 2026-11-12

- Room card takes the section's full width by default

## 0.15.2 – 2026-11-12

- Room card and its editor work before a room is chosen

## 0.15.1 – 2026-11-12

- Room card names every reason
- Card background

## 0.15.0 – 2026-11-12

- Room card (dial, boost, +/-, the day) and the companion integration whose services are never learned from

## 0.14.1 – 2026-11-12

- Aqara W600 takes the room temperature too

## 0.14.0 – 2026-11-12

- Room temperature to the valves, too-warm warning, battery by voltage, forget a learned comfort

## 0.13.6 – 2026-11-12

- A valve swapping temperature sensor (Aqara E1) isn't taken as turning by hand

## 0.13.5 – 2026-11-11

- Room settings follow water floor heating: setback and night shown and chosen at most 2 degrees below comfort, following comfort up, with a short note

## 0.13.4 – 2026-11-11

- Water floor heating never more than 2 degrees below comfort (slow floors)
- Electric floor heating (measures its own power) sets back freely

## 0.13.3 – 2026-11-11

- No blink every 30 s: pages fade in only when opened, not when the numbers refresh

## 0.13.2 – 2026-11-11

- Livelier front page: sky with sun or moon on its arc, drifting clouds after the forecast, rain and snow, stars
- Tiled roof with the chimney on it and smoke by how many rooms heat
- Lamps in occupied rooms
- House first, warnings folded into one line
- Names never cut

## 0.13.1 – 2026-11-11

- Sun per hour from the best forecast the home has (Solcast, Open-Meteo, Energy dashboard/Forecast.Solar, cloud cover, weather)
- Sun gain learned as a clear day's

## 0.13.0 – 2026-11-10

- Simpler: front page with the extras under More
- Settings in four folded groups with adjustments behind Adjust
- Room page with comfort, hours and night up front
- Plain words
- One button to control the whole house

## 0.12.0 – 2026-11-10

- Control room by room (shadow first, only what changes, cloud pace, retry, echo guard, summer valve exercise)
- °F homes
- 7 languages
- Night hours to choose
- Thermostats without a room become rooms
- Docker
- README

## 0.11.3 – 2026-11-10

- Smoke rises from the chimney top (chimney in front of the roof), clearer

## 0.11.2 – 2026-11-10

- No kr per MWh until the utility's bonus/penalty is set
- Warm-on-time shown once Heat Pilot controls (in shadow another system heats)

## 0.11.1 – 2026-11-10

- District heating: the live supply/return, never a monthly/yearly average (Kamstrup readers have both)
- Kept cooling starts over when the meter sensor changes

## 0.11.0 – 2026-11-10

- Welcome guide
- Room page with plain-language why and a 48-hour chart
- Clearer Plan tab (full names, temperatures, real times, tap a room)
- Savings in plain words
- Rooms open by address

## 0.10.1 – 2026-11-10

- Fix: room kinds shown in the language again (clashed with message names)
- Heating type shown and chosen right

## 0.10.0 – 2026-11-10

- The rest from AppDaemon, made general: evening comfort, learned comfort, room heat-loss model, sun model, cold snap, no-show, strategies, floor heating follows the floor, floor buffer for district heating, doors vs windows (and doors chosen per room)

## 0.9.1 – 2026-11-10

- Holiday text without the fixed time

## 0.9.0 – 2026-11-10

- Adjustable: easy choices under each feature and in General
- Rooms with − / + and hour pickers

## 0.8.0 – 2026-11-10

- Step 7: house drawn by floors (basement below ground), roof, smoke, sun/moon
- Home Assistant's language
- Bigger rooms on phones
- Dashboard card + sensor.varmepilot
- Monthly report

## 0.7.0 – 2026-11-10

- Step 6: warnings (mould, air, window, offline, battery, not warming, district cooling) shown in the app
- Messages only to chosen phones, each kind can be turned off, no repeats, quiet at night

## 0.6.0 – 2026-11-10

- Step 5: ventilation found across brands (levels, four temperatures, bypass)
- Boost after shower, CO2/humidity, free cooling
- No heating while it or another system cools

## 0.5.0 – 2026-11-10

- Step 4: district heating cooling (meter found by itself, weighted by water, bonus/penalty, gentle heat-up when poor)
- Electric rooms follow the price
- Published for Energy Pilot

## 0.4.0 – 2026-11-10

- Step 3: people (phones away, on the way home, whose room), holiday (long away or calendar), summer off

## 0.3.0 – 2026-11-10

- Step 2: CO2/humidity/lights, shower hold, sun, weather-aware heat-up, front door away, turned by hand with echo guard
- Features found by themselves, can be turned off, hidden when missing

## 0.2.0 – 2026-11-10

- Smarter: learns when rooms are used (10 days of history at once) and how fast they heat, starts in time
- New look with house, sentence, metrics, plan

## 0.1.0 – 2026-11-10

- Heat Pilot, step 1: finds rooms, thermostats and sensors
- Brand profiles
- Shadow plan and panel
- Add-on: config, Dockerfile, docs, CI
