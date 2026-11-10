"""People and the year: everyone away, on the way home, whose room, holidays and summer."""

from datetime import datetime, timedelta, timezone

from heat_pilot import people, plan

NOW = datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc)


def person(state, hours_ago=1, name="Dennis"):
    return {"state": state, "last_changed": (NOW - timedelta(hours=hours_ago)).isoformat(),
            "attributes": {"device_trackers": ["device_tracker.phone"], "friendly_name": name}}


def test_everyone_away_and_holiday_after_a_day():
    st = {"person.dennis": person("not_home", 2), "person.claus": person("work", 3, "Claus")}
    ps = people.persons(st)
    assert people.all_away(st, ps)
    assert people.holiday(st, ps, NOW, True) is None
    st["person.dennis"] = person("not_home", 30)
    st["person.claus"] = person("not_home", 26, "Claus")
    assert people.holiday(st, ps, NOW, True) == "away_long"
    st["person.claus"] = person("home", 1, "Claus")
    assert not people.all_away(st, ps) and people.holiday(st, ps, NOW, True) is None


def test_untracked_person_does_not_count():
    st = {"person.guest": {"state": "unknown", "attributes": {}}, "person.dennis": person("home")}
    assert people.persons(st) == ["person.dennis"]


def test_calendar_holiday():
    st = {"calendar.family": {"state": "on", "attributes": {"message": "Ferie i Spanien"}}}
    assert people.holiday(st, [], NOW, True) == "calendar"
    st["calendar.family"]["attributes"]["message"] = "Tandlæge"
    assert people.holiday(st, [], NOW, True) is None


def test_coming_home_with_proximity():
    st = {"person.dennis": person("not_home"),
          "sensor.home_dennis_direction_of_travel": {"state": "towards"},
          "sensor.home_dennis_distance": {"state": "8000", "attributes": {"unit_of_measurement": "m"}}}
    assert people.coming_home(st, ["person.dennis"]) == ["person.dennis"]
    st["sensor.home_dennis_distance"]["state"] = "40000"
    assert people.coming_home(st, ["person.dennis"]) == []


def test_room_owner_from_name():
    st = {"person.dennis": person("home"), "person.simone_h": person("home", name="Simone Hansen")}
    ps = people.persons(st)
    assert people.owner_of("Dennis værelse", ps, st) == "person.dennis"
    assert people.owner_of("Simone", ps, st) == "person.simone_h"
    assert people.owner_of("Stue", ps, st) is None


def test_summer_after_three_warm_days():
    days = {"2026-07-01": 18.0, "2026-07-02": 17.5, "2026-07-03": 16.9}
    assert people.summer(days, datetime(2026, 7, 4, 12, tzinfo=timezone.utc))
    days["2026-07-03"] = 12.0
    assert not people.summer(days, datetime(2026, 7, 4, 12, tzinfo=timezone.utc))


def test_plan_layers():
    room = {"kind": "kids", "windows": []}
    assert plan.target(room, {}, {}, NOW, False, None, summer=True)["why"] == "summer"
    assert plan.target(room, {}, {}, NOW, False, None, holiday="away_long") == {"temp": 15.0, "why": "holiday", "kind": "away_long"}
    assert plan.target(room, {}, {}, NOW, False, None, owner_away=True)["why"] == "owner_away"
    assert plan.target(room, {}, {}, NOW, True, None)["why"] == "away"
    assert plan.target(room, {}, {}, NOW, True, None, coming=True)["why"] == "comfort"


def test_shared_room_needs_everyone_and_all_away():
    st = {"person.lilly": person("home", name="Lilly"), "person.holly": person("home", name="Holly")}
    assert people.owner_of("Holly & Lilly", ["person.lilly"], st) is None  # Holly isn't tracked: can't know
    o = people.owner_of("Holly & Lilly", ["person.holly", "person.lilly"], st)
    assert o == "person.holly,person.lilly"
    st["person.lilly"] = person("not_home", name="Lilly")
    assert not people.owners_away(st, o)
    st["person.holly"] = person("not_home", name="Holly")
    assert people.owners_away(st, o)
