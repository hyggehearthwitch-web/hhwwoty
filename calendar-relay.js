/**
 * A Hygge Hearth Witch's Wheel of the Year — calendar relay.
 * Read-only. Returns the calendar's events as JSON for the web app.
 */
var CALENDAR_ID =
  'd17d283695b8526d94cc74c78d0554050cb70c04f982e4c1dd018668db6d4f2a@group.calendar.google.com';
var TZ = 'America/Edmonton';

function doGet() {
  var cal = CalendarApp.getCalendarById(CALENDAR_ID);
  var now = new Date();
  var from = new Date(now.getFullYear() - 1, 0, 1);
  var to = new Date(now.getFullYear() + 3, 0, 1);

  var out = cal.getEvents(from, to).map(function (ev, i) {
    var allDay = ev.isAllDayEvent();
    var date = allDay
      ? Utilities.formatDate(ev.getAllDayStartDate(), 'UTC', 'yyyy-MM-dd')
      : Utilities.formatDate(ev.getStartTime(), TZ, 'yyyy-MM-dd');
    return {
      id: (ev.getId() || ('e' + i)) + ':' + date,
      date: date,
      title: ev.getTitle() || '(untitled)',
      description: ev.getDescription() || '',
      url: '',
      time: allDay ? null : Utilities.formatDate(ev.getStartTime(), TZ, 'HH:mm'),
      allDay: allDay,
      srcTz: TZ
    };
  });

  return ContentService.createTextOutput(
    JSON.stringify({ timezone: TZ, count: out.length, events: out })
  ).setMimeType(ContentService.MimeType.JSON);
}
