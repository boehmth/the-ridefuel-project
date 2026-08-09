/**
 * TrainingsPlanner – Frontend-Logik (Vanilla JavaScript)
 *
 * Implementiert den Kalender (Tag/Woche/Monat/Jahr) mit integrierten
 * Aktivitäten und Mahlzeiten, die Listenansicht, die Mahlzeiten-Eingabe
 * mit KI-Kalorien-Schätzung und das Strava-Panel.
 */

// ============================================================
// Konfiguration
// ============================================================

const EVENT_TYPE_CONFIG = {
  training: { label: 'Training', color: '#e74c3c', symbol: '🏃' },
  nutrition: { label: 'Ernährung', color: '#27ae60', symbol: '🍽️' },
  sleep: { label: 'Schlaf', color: '#8e44ad', symbol: '😴' },
  weight: { label: 'Gewicht', color: '#f39c12', symbol: '⚖️' },
  body: { label: 'Körperwerte', color: '#16a085', symbol: '📏' },
  regeneration: { label: 'Regeneration', color: '#2980b9', symbol: '💆' },
  illness: { label: 'Krankheit', color: '#c0392b', symbol: '🤒' },
  appointment: { label: 'Termin', color: '#2c3e50', symbol: '📅' },
  medication: { label: 'Medikamente', color: '#7f8c8d', symbol: '💊' },
  note: { label: 'Notiz', color: '#95a5a6', symbol: '📝' },
};

// Farben für Aktivitäten und Mahlzeiten
const ACTIVITY_COLOR = '#e8590c'; // Kräftiges Orange (Strava)
const MEAL_COLOR = '#2f9e44'; // Kräftiges Grün


const WEEKDAY_LABELS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
const MONTH_LABELS = [
  'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
];

const HOUR_HEIGHT = 60;
const MAX_TILES_PER_DAY = 4;

// ============================================================
// Datums-Hilfsfunktionen
// ============================================================

function toISODate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function startOfWeek(date) {
  const day = date.getDay(); // 0 = Sonntag
  const diff = day === 0 ? -6 : 1 - day; // Woche beginnt am Montag
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + diff);
}

function startOfMonth(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function addDays(date, days) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);
}

function addMonths(date, months) {
  return new Date(date.getFullYear(), date.getMonth() + months, 1);
}

function addYears(date, years) {
  return new Date(date.getFullYear() + years, date.getMonth(), 1);
}

function isSameMonth(a, b) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth();
}

function daysInMonth(date) {
  return new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate();
}

function formatTime(iso) {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function formatTitle(view, date) {
  switch (view) {
    case 'week':
    case 'month':
      return `${MONTH_LABELS[date.getMonth()]} ${date.getFullYear()}`;
    case 'year':
      return String(date.getFullYear());
  }
}

/**
 * Filtert Kalender-Items nach dem aktuellen Zeitraum (Woche/Monat/Jahr).
 */
function filterItemsByView(view, date, items) {
  if (view === 'week') {
    const weekStart = startOfWeek(date);
    const weekEnd = addDays(weekStart, 6);
    const startKey = toISODate(weekStart);
    const endKey = toISODate(weekEnd);
    return items.filter((i) => {
      const key = toISODate(new Date(i.start));
      return key >= startKey && key <= endKey;
    });
  } else if (view === 'month') {
    const monthStart = startOfMonth(date);
    const monthEnd = new Date(date.getFullYear(), date.getMonth() + 1, 0);
    const startKey = toISODate(monthStart);
    const endKey = toISODate(monthEnd);
    return items.filter((i) => {
      const key = toISODate(new Date(i.start));
      return key >= startKey && key <= endKey;
    });
  } else if (view === 'year') {
    const year = date.getFullYear();
    return items.filter((i) => {
      const d = new Date(i.start);
      return d.getFullYear() === year;
    });
  }
  return items;
}



// ============================================================
// API-Hilfsfunktionen
// ============================================================

async function apiGet(url) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

async function apiPost(url, body) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

async function apiDelete(url) {
  const resp = await fetch(url, { method: 'DELETE' });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
}

// ============================================================
// App-Zustand
// ============================================================

const state = {
  view: 'week',
  displayMode: 'calendar', // 'calendar' | 'list'
  currentDate: new Date(),
  selectedDate: new Date(), // für Mahlzeiten-Eingabe ausgewählter Tag
  events: [],
  meals: [],
  activities: [],
  calendarItems: [], // kombinierte Items aus /api/calendar
  stravaAuthenticated: false,
  auth: {
    authenticated: false,
    user: null,
  },
};



// ============================================================
// Überlappungs-Layout-Algorithmus
// ============================================================

/**
 * Berechnet für überlappende Events ein Layout, sodass sie
 * nebeneinander angezeigt werden (wie in Outlook).
 *
 * @param {Array} items - Events mit start/end (Date-Objekte)
 * @returns {Array} items mit left/width (in %)
 */
function computeOverlapLayout(items) {
  if (items.length === 0) return [];

  // Sortieren nach Startzeit
  const sorted = [...items].sort((a, b) => a.start - b.start || a.end - b.end);

  // Gruppen von überlappenden Events bilden
  const groups = [];
  let currentGroup = [sorted[0]];

  for (let i = 1; i < sorted.length; i++) {
    const prev = sorted[i - 1];
    const curr = sorted[i];
    if (curr.start < prev.end) {
      currentGroup.push(curr);
    } else {
      groups.push(currentGroup);
      currentGroup = [curr];
    }
  }
  groups.push(currentGroup);

  // Für jede Gruppe Spalten zuweisen
  const result = [];
  for (const group of groups) {
    const columns = [];
    for (const item of group) {
      let col = 0;
      while (columns[col] && columns[col].end > item.start) {
        col++;
      }
      if (!columns[col]) columns[col] = { end: item.end };
      else columns[col].end = Math.max(columns[col].end, item.end);

      item.column = col;
      item.totalColumns = Math.max(group.length, columns.length);
    }
    result.push(...group);
  }

  // left/width berechnen
  for (const item of result) {
    const total = item.totalColumns || 1;
    item.left = (item.column / total) * 100;
    item.width = (1 / total) * 100;
  }

  return result;
}

// ============================================================
// Kalender-Item-Tile
// ============================================================

function createCalendarItemTile(item, compact = false) {
  const tile = document.createElement('div');
  tile.className = `calendar-tile calendar-tile--${item.type}`;

  // Farbe je nach Typ
  let color;
  let symbol;
  if (item.type === 'activity') {
    color = ACTIVITY_COLOR;
    symbol = '🏃';
  } else if (item.type === 'meal') {
    color = MEAL_COLOR;
    symbol = '🍽️';
  } else {
    const config = EVENT_TYPE_CONFIG[item.event_type] || EVENT_TYPE_CONFIG.note;
    color = config.color;
    symbol = config.symbol;
  }
  tile.style.backgroundColor = color;

  // Tooltip
  let tooltip = '';
  if (item.type === 'activity') {
    const km = item.metadata?.distance_km ?? (item.distance_m / 1000).toFixed(2);
    const min = item.metadata?.moving_time_min ?? Math.round(item.moving_time_s / 60);
    const kcal = item.metadata?.calories ?? item.calories ?? '–';
    tooltip = `${item.title}\n${formatTime(item.start)} – ${formatTime(item.end)}\n${km} km · ${min} min · ${kcal} kcal`;
  } else if (item.type === 'meal') {
    const kcal = item.metadata?.calories ?? item.calories ?? '–';
    const p = item.metadata?.protein_g ?? item.protein_g;
    const c = item.metadata?.carbs_g ?? item.carbs_g;
    const f = item.metadata?.fat_g ?? item.fat_g;
    let macros = '';
    if (p != null || c != null || f != null) {
      const parts = [];
      if (p != null) parts.push(`${p}g Protein`);
      if (c != null) parts.push(`${c}g KH`);
      if (f != null) parts.push(`${f}g Fett`);
      macros = `\n${parts.join(' · ')}`;
    }
    tooltip = `${item.title}\n${formatTime(item.start)} – ${formatTime(item.end)}\n${kcal} kcal${macros}`;
  } else {
    tooltip = `${item.title}\n${formatTime(item.start)} – ${formatTime(item.end)}`;
  }
  tile.title = tooltip;


  const symbolEl = document.createElement('span');
  symbolEl.className = 'calendar-tile__symbol';
  symbolEl.textContent = symbol;
  tile.appendChild(symbolEl);

  const content = document.createElement('div');
  content.className = 'calendar-tile__content';

  if (!compact) {
    const time = document.createElement('span');
    time.className = 'calendar-tile__time';
    time.textContent = `${formatTime(item.start)} – ${formatTime(item.end)}`;
    content.appendChild(time);
  }

  // Titel
  const title = document.createElement('span');
  title.className = 'calendar-tile__title';
  if (item.type === 'meal') {
    // Bei Mahlzeiten: kcal + Makros anzeigen
    const kcal = item.metadata?.calories ?? item.calories ?? '–';
    const p = item.metadata?.protein_g ?? item.protein_g;
    const c = item.metadata?.carbs_g ?? item.carbs_g;
    const f = item.metadata?.fat_g ?? item.fat_g;
    let macrosText = '';
    if (p != null || c != null || f != null) {
      const parts = [];
      if (p != null) parts.push(`${p}g P`);
      if (c != null) parts.push(`${c}g KH`);
      if (f != null) parts.push(`${f}g F`);
      macrosText = ` · ${parts.join(' · ')}`;
    }
    title.textContent = `${kcal} kcal${macrosText}`;
  } else if (item.type === 'activity') {


    // Bei Aktivitäten: Zeit, Strecke, kcal
    const km = item.metadata?.distance_km ?? (item.distance_m / 1000).toFixed(2);
    const min = item.metadata?.moving_time_min ?? Math.round(item.moving_time_s / 60);
    const kcal = item.metadata?.calories ?? item.calories ?? '–';
    title.textContent = `${km} km · ${min} min · ${kcal} kcal`;
  } else {
    title.textContent = item.title;
  }
  content.appendChild(title);


  tile.appendChild(content);
  return tile;
}

// ============================================================
// Wochenansicht (mit Aktivitäten & Mahlzeiten)
// ============================================================


function renderWeekView(container, date, items) {
  const weekStart = startOfWeek(date);
  const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));

  const view = document.createElement('div');
  view.className = 'week-view';

  // Header
  const header = document.createElement('div');
  header.className = 'week-view__header';

  const corner = document.createElement('div');
  corner.className = 'week-view__corner';
  header.appendChild(corner);

  days.forEach((day, index) => {
    const dayHeader = document.createElement('div');
    dayHeader.className = 'week-view__day-header';
    // Klick auf Tag wählt den Tag für Mahlzeiten-Eingabe aus
    dayHeader.style.cursor = 'pointer';
    dayHeader.title = 'Tag für Mahlzeiten-Eingabe auswählen';
    dayHeader.addEventListener('click', () => {
      state.selectedDate = new Date(day.getFullYear(), day.getMonth(), day.getDate());
      loadMeals(state.selectedDate).then(() => renderCalendar());
    });

    const weekday = document.createElement('span');
    weekday.className = 'week-view__weekday';
    weekday.textContent = WEEKDAY_LABELS[index];
    dayHeader.appendChild(weekday);

    const dayNumber = document.createElement('span');
    dayNumber.className = 'week-view__day-number';
    dayNumber.textContent = day.getDate();
    dayHeader.appendChild(dayNumber);

    // Ausgewählten Tag hervorheben
    if (toISODate(day) === toISODate(state.selectedDate)) {
      dayHeader.style.backgroundColor = '#eef2ff';
      dayHeader.style.borderRadius = '4px';
    }

    header.appendChild(dayHeader);
  });


  view.appendChild(header);

  // Body
  const body = document.createElement('div');
  body.className = 'week-view__body';

  // Zeit-Spalte (nur 07:00 – 19:00 Uhr anzeigen)
  // TODO: Zeitbereich später benutzerdefiniert machen
  const VIEW_START_HOUR = 7;
  const VIEW_END_HOUR = 19;

  const VIEW_START_MIN = VIEW_START_HOUR * 60;
  const VIEW_END_MIN = VIEW_END_HOUR * 60;
  const VIEW_DURATION_MIN = VIEW_END_MIN - VIEW_START_MIN;

  const timeColumn = document.createElement('div');
  timeColumn.className = 'week-view__time-column';
  for (let h = VIEW_START_HOUR; h <= VIEW_END_HOUR; h++) {
    const label = document.createElement('div');
    label.className = 'week-view__time-label';
    label.textContent = `${String(h).padStart(2, '0')}:00`;
    timeColumn.appendChild(label);
  }
  body.appendChild(timeColumn);


  // Tage
  days.forEach((day) => {
    const dayKey = toISODate(day);
    const dayItems = items.filter((i) => toISODate(new Date(i.start)) === dayKey);

    const dayCol = document.createElement('div');
    dayCol.className = 'week-view__day';

    // Nur Stunden im sichtbaren Bereich anzeigen
    for (let h = VIEW_START_HOUR; h <= VIEW_END_HOUR; h++) {
      const hour = document.createElement('div');
      hour.className = 'week-view__hour';
      dayCol.appendChild(hour);
    }

    // Überlappungs-Layout berechnen
    const laidOut = computeOverlapLayout(
      dayItems.map((i) => ({
        ...i,
        start: new Date(i.start),
        end: new Date(i.end),
      }))
    );

    laidOut.forEach((item) => {
      const start = item.start;
      const end = item.end;
      const startMinutes = start.getHours() * 60 + start.getMinutes();
      const endMinutes = end.getHours() * 60 + end.getMinutes();

      // Position relativ zum sichtbaren Bereich (07:00 – 19:00)

      const relStart = Math.max(startMinutes, VIEW_START_MIN);
      const relEnd = Math.min(endMinutes, VIEW_END_MIN);
      const top = ((relStart - VIEW_START_MIN) / VIEW_DURATION_MIN) * (VIEW_DURATION_MIN / 60) * HOUR_HEIGHT;
      const height = Math.max(((relEnd - relStart) / VIEW_DURATION_MIN) * (VIEW_DURATION_MIN / 60) * HOUR_HEIGHT, 24);

      const wrapper = document.createElement('div');
      wrapper.className = 'week-view__event';
      wrapper.style.top = `${top}px`;
      wrapper.style.height = `${height}px`;
      wrapper.style.left = `${item.left}%`;
      wrapper.style.width = `${item.width}%`;
      wrapper.appendChild(createCalendarItemTile(item));
      dayCol.appendChild(wrapper);
    });

    body.appendChild(dayCol);
  });


  view.appendChild(body);
  container.appendChild(view);
}

// ============================================================
// Monatsansicht (mit Aktivitäten & Mahlzeiten)
// ============================================================

function renderMonthView(container, date, items) {
  const monthStart = startOfMonth(date);
  const gridStart = startOfWeek(monthStart);
  const days = Array.from({ length: 42 }, (_, i) => addDays(gridStart, i));

  const view = document.createElement('div');
  view.className = 'month-view';

  // Header
  const header = document.createElement('div');
  header.className = 'month-view__header';
  WEEKDAY_LABELS.forEach((label) => {
    const weekday = document.createElement('div');
    weekday.className = 'month-view__weekday';
    weekday.textContent = label;
    header.appendChild(weekday);
  });
  view.appendChild(header);

  // Grid
  const grid = document.createElement('div');
  grid.className = 'month-view__grid';

  days.forEach((day) => {
    const dayKey = toISODate(day);
    const dayItems = items.filter((i) => toISODate(new Date(i.start)) === dayKey);
    const visibleItems = dayItems.slice(0, MAX_TILES_PER_DAY);
    const hiddenCount = dayItems.length - visibleItems.length;
    const inMonth = isSameMonth(day, date);

    const cell = document.createElement('div');
    cell.className = `month-view__cell${inMonth ? '' : ' month-view__cell--outside'}`;
    // Klick auf Tag wählt den Tag für Mahlzeiten-Eingabe aus
    cell.style.cursor = 'pointer';
    cell.title = 'Tag für Mahlzeiten-Eingabe auswählen';
    cell.addEventListener('click', () => {
      state.selectedDate = new Date(day.getFullYear(), day.getMonth(), day.getDate());
      loadMeals(state.selectedDate).then(() => renderCalendar());
    });

    const dayNumber = document.createElement('span');
    dayNumber.className = 'month-view__day-number';
    dayNumber.textContent = day.getDate();
    cell.appendChild(dayNumber);

    // Ausgewählten Tag hervorheben
    if (toISODate(day) === toISODate(state.selectedDate)) {
      cell.style.backgroundColor = '#eef2ff';
    }


    const tiles = document.createElement('div');
    tiles.className = 'month-view__tiles';

    visibleItems.forEach((item) => {
      tiles.appendChild(createCalendarItemTile(item, true));
    });

    if (hiddenCount > 0) {
      const more = document.createElement('span');
      more.className = 'month-view__more';
      more.textContent = `+${hiddenCount} weitere`;
      tiles.appendChild(more);
    }

    cell.appendChild(tiles);
    grid.appendChild(cell);
  });

  view.appendChild(grid);
  container.appendChild(view);
}

// ============================================================
// Jahresansicht (mit Aktivitäten & Mahlzeiten)
// ============================================================

function renderYearView(container, date, items) {
  const year = date.getFullYear();
  const eventDays = new Set(items.map((i) => toISODate(new Date(i.start))));

  const view = document.createElement('div');
  view.className = 'year-view';

  const title = document.createElement('h2');
  title.className = 'year-view__title';
  title.textContent = year;
  view.appendChild(title);

  const grid = document.createElement('div');
  grid.className = 'year-view__grid';

  for (let m = 0; m < 12; m++) {
    const monthDate = new Date(year, m, 1);
    const monthStart = startOfWeek(startOfMonth(monthDate));
    const count = daysInMonth(monthDate);
    const offset = monthStart.getDay() === 0 ? 6 : monthStart.getDay() - 1;
    const total = Math.ceil((offset + count) / 7) * 7;
    const monthDays = Array.from({ length: total }, (_, i) => addDays(monthStart, i));

    const monthDiv = document.createElement('div');
    monthDiv.className = 'year-view__month';

    const monthTitle = document.createElement('h3');
    monthTitle.className = 'year-view__month-title';
    monthTitle.textContent = MONTH_LABELS[m];
    monthDiv.appendChild(monthTitle);

    const weekdays = document.createElement('div');
    weekdays.className = 'year-view__weekdays';
    WEEKDAY_LABELS.forEach((label) => {
      const wd = document.createElement('span');
      wd.className = 'year-view__weekday';
      wd.textContent = label;
      weekdays.appendChild(wd);
    });
    monthDiv.appendChild(weekdays);

    const daysDiv = document.createElement('div');
    daysDiv.className = 'year-view__days';

    monthDays.forEach((day) => {
      const key = toISODate(day);
      const hasEvents = eventDays.has(key);
      const inMonth = day.getMonth() === m;

      const daySpan = document.createElement('span');
      daySpan.className = `year-view__day${inMonth ? '' : ' year-view__day--outside'}${
        hasEvents ? ' year-view__day--has-events' : ''
      }`;
      daySpan.textContent = day.getDate();
      daysDiv.appendChild(daySpan);
    });

    monthDiv.appendChild(daysDiv);
    grid.appendChild(monthDiv);
  }

  view.appendChild(grid);
  container.appendChild(view);
}

// ============================================================
// Listenansicht
// ============================================================

function renderListView(container, date, items) {
  const view = document.createElement('div');
  view.className = 'list-view';

  // Items nach aktuellem View filtern
  const filteredItems = filterItemsByView(state.view, date, items);

  // Titel je nach View
  let titleText;
  if (state.view === 'week') {
    const weekStart = startOfWeek(date);
    const weekEnd = addDays(weekStart, 6);
    titleText = `Alle Einträge – KW ${weekStart.getDate()}. ${MONTH_LABELS[weekStart.getMonth()]} – ${weekEnd.getDate()}. ${MONTH_LABELS[weekEnd.getMonth()]}`;
  } else if (state.view === 'month') {
    titleText = `Alle Einträge – ${MONTH_LABELS[date.getMonth()]} ${date.getFullYear()}`;
  } else {
    titleText = `Alle Einträge – ${date.getFullYear()}`;
  }

  const title = document.createElement('h2');
  title.className = 'list-view__title';
  title.textContent = titleText;
  view.appendChild(title);

  // Nach Datum gruppieren
  const grouped = {};
  filteredItems.forEach((item) => {
    const key = toISODate(new Date(item.start));
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(item);
  });


  const sortedKeys = Object.keys(grouped).sort();

  if (sortedKeys.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'list-view__empty';
    empty.textContent = 'Keine Einträge für diesen Zeitraum.';
    view.appendChild(empty);
    container.appendChild(view);
    return;
  }

  sortedKeys.forEach((key) => {
    const [y, m, d] = key.split('-').map(Number);
    const dayDate = new Date(y, m - 1, d);

    const daySection = document.createElement('div');
    daySection.className = 'list-view__day';

    const dayHeader = document.createElement('div');
    dayHeader.className = 'list-view__day-header';
    dayHeader.textContent = `${d}. ${MONTH_LABELS[m - 1]} ${y}`;
    daySection.appendChild(dayHeader);

    const dayItems = grouped[key].sort((a, b) => new Date(a.start) - new Date(b.start));

    dayItems.forEach((item) => {
      const row = document.createElement('div');
      row.className = `list-view__row list-view__row--${item.type}`;

      const time = document.createElement('span');
      time.className = 'list-view__row-time';
      time.textContent = formatTime(item.start);
      row.appendChild(time);

      const info = document.createElement('div');
      info.className = 'list-view__row-info';

      const name = document.createElement('div');
      name.className = 'list-view__row-name';
      if (item.type === 'meal') {
        const kcal = item.metadata?.calories ?? item.calories ?? '–';
        const p = item.metadata?.protein_g ?? item.protein_g;
        const c = item.metadata?.carbs_g ?? item.carbs_g;
        const f = item.metadata?.fat_g ?? item.fat_g;
        let macrosText = '';
        if (p != null || c != null || f != null) {
          const parts = [];
          if (p != null) parts.push(`${p}g P`);
          if (c != null) parts.push(`${c}g KH`);
          if (f != null) parts.push(`${f}g F`);
          macrosText = ` · ${parts.join(' · ')}`;
        }
        name.textContent = `${kcal} kcal${macrosText}`;
      } else if (item.type === 'activity') {

        const km = item.metadata?.distance_km ?? (item.distance_m / 1000).toFixed(2);
        const min = item.metadata?.moving_time_min ?? Math.round(item.moving_time_s / 60);
        const kcal = item.metadata?.calories ?? item.calories ?? '–';
        name.textContent = `${item.title} · ${km} km · ${min} min · ${kcal} kcal`;
      } else {
        name.textContent = item.title;
      }
      info.appendChild(name);

      const meta = document.createElement('div');
      meta.className = 'list-view__row-meta';
      if (item.type === 'meal') {
        meta.textContent = 'Mahlzeit';
      } else if (item.type === 'activity') {
        meta.textContent = `Aktivität · ${item.activity_type || ''}`;
      } else {
        const config = EVENT_TYPE_CONFIG[item.event_type] || EVENT_TYPE_CONFIG.note;
        meta.textContent = config.label;
      }
      info.appendChild(meta);

      row.appendChild(info);

      // Löschen-Button für Mahlzeiten
      if (item.type === 'meal') {
        const delBtn = document.createElement('button');
        delBtn.className = 'list-view__row-delete';
        delBtn.textContent = '✕';
        delBtn.title = 'Löschen';
        delBtn.addEventListener('click', async () => {
          try {
            await apiDelete(`/api/meals/${item.source_id}`);
            await loadAllData();
          } catch (err) {
            console.error('Löschen fehlgeschlagen:', err);
          }
        });
        row.appendChild(delBtn);
      }

      daySection.appendChild(row);
    });

    view.appendChild(daySection);

  });

  container.appendChild(view);
}

// ============================================================
// Mahlzeiten-Panel
// ============================================================


function renderMealsPanel(container, date) {

  const panel = document.createElement('div');
  panel.className = 'meals-panel';

  const title = document.createElement('h2');
  title.className = 'meals-panel__title';
  title.textContent = `Mahlzeiten – ${date.getDate()}. ${MONTH_LABELS[date.getMonth()]}`;
  panel.appendChild(title);

  // Formular
  const form = document.createElement('form');
  form.className = 'meals-panel__form';

  const input = document.createElement('input');
  input.className = 'meals-panel__input';
  input.type = 'text';
  input.placeholder = 'z. B. "2 Scheiben Vollkornbrot mit Käse"';
  input.required = true;
  form.appendChild(input);

  const submit = document.createElement('button');
  submit.className = 'meals-panel__submit';
  submit.type = 'submit';
  submit.textContent = 'Hinzufügen';
  form.appendChild(submit);

  panel.appendChild(form);

  // Schätzungs-Anzeige
  const estimateDiv = document.createElement('div');
  estimateDiv.className = 'meals-panel__estimate';
  estimateDiv.style.display = 'none';
  panel.appendChild(estimateDiv);

  // Liste
  const list = document.createElement('div');
  list.className = 'meals-panel__list';
  panel.appendChild(list);

  // Gesamtsumme
  const total = document.createElement('div');
  total.className = 'meals-panel__total';
  panel.appendChild(total);

  // Formular-Handler
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const description = input.value.trim();
    if (!description) return;

    submit.disabled = true;
    submit.textContent = 'Schätze…';
    estimateDiv.style.display = 'block';
    estimateDiv.textContent = 'KI berechnet Kalorien…';

    try {
      // Lokale Tagesangabe (YYYY-MM-DD) senden, NICHT date.toISOString().
      // toISOString() liefert UTC und verschiebt die Uhrzeit bei der Anzeige
      // (z. B. 12:00 → 14:00), weil der Server in UTC läuft.
      const meal = await apiPost('/api/meals', {
        date: toISODate(date),
        description,
      });

      input.value = '';
      // Erfolgsmeldung kurz anzeigen
      estimateDiv.textContent = `✓ ${meal.calories} kcal geschätzt – Mahlzeit gespeichert`;
      estimateDiv.style.backgroundColor = '#f0fdf4';
      estimateDiv.style.borderColor = '#bbf7d0';
      estimateDiv.style.color = '#166534';
      await loadAllData();
      // Nach 3 Sekunden ausblenden
      setTimeout(() => {
        estimateDiv.style.display = 'none';
      }, 3000);
    } catch (err) {
      // Eingabekorrektur: Wenn das LLM die Eingabe nicht versteht (422)
      estimateDiv.textContent = `⚠️ ${err.message}`;
      estimateDiv.style.backgroundColor = '#fffbeb';
      estimateDiv.style.borderColor = '#fde68a';
      estimateDiv.style.color = '#92400e';
      input.focus();
    } finally {

      submit.disabled = false;
      submit.textContent = 'Hinzufügen';
    }
  });

  container.appendChild(panel);
}

function renderMealsList(listEl, totalEl, meals) {
  listEl.innerHTML = '';
  const dayMeals = meals;

  if (dayMeals.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'meals-panel__item';
    empty.textContent = 'Noch keine Mahlzeiten für diesen Tag.';
    listEl.appendChild(empty);
  }

  let totalCalories = 0;

  dayMeals.forEach((meal) => {
    totalCalories += meal.calories;

    const item = document.createElement('div');
    item.className = 'meals-panel__item';

    const info = document.createElement('div');
    info.className = 'meals-panel__item-info';

    const desc = document.createElement('div');
    desc.className = 'meals-panel__item-desc';
    const mealTime = formatTime(meal.date);
    desc.textContent = `${mealTime} · ${meal.description}`;
    info.appendChild(desc);

    const meta = document.createElement('div');
    meta.className = 'meals-panel__item-meta';
    const macros = [];
    if (meal.protein_g != null) macros.push(`${meal.protein_g}g Protein`);
    if (meal.carbs_g != null) macros.push(`${meal.carbs_g}g KH`);
    if (meal.fat_g != null) macros.push(`${meal.fat_g}g Fett`);
    meta.textContent = macros.length > 0 ? macros.join(' · ') : `via ${meal.provider}`;
    info.appendChild(meta);


    item.appendChild(info);

    const calories = document.createElement('span');
    calories.className = 'meals-panel__item-calories';
    calories.textContent = `${meal.calories} kcal`;
    item.appendChild(calories);

    const delBtn = document.createElement('button');
    delBtn.className = 'meals-panel__item-delete';
    delBtn.textContent = '✕';
    delBtn.title = 'Löschen';
    delBtn.addEventListener('click', async () => {
      try {
        await apiDelete(`/api/meals/${meal.id}`);
        await loadAllData();
      } catch (err) {
        console.error('Löschen fehlgeschlagen:', err);
      }
    });
    item.appendChild(delBtn);

    listEl.appendChild(item);
  });

  totalEl.textContent = `Gesamt: ${totalCalories} kcal`;
}

// ============================================================
// Strava-Panel
// ============================================================

function renderStravaPanel(container) {
  const panel = document.createElement('div');
  panel.className = 'strava-panel';

  const title = document.createElement('h2');
  title.className = 'strava-panel__title';
  title.textContent = 'Strava Aktivitäten';
  panel.appendChild(title);

  const actions = document.createElement('div');
  actions.className = 'strava-panel__actions';

  if (!state.stravaAuthenticated) {
    const connectBtn = document.createElement('button');
    connectBtn.className = 'strava-panel__button strava-panel__button--primary';
    connectBtn.textContent = 'Mit Strava verbinden';
    connectBtn.addEventListener('click', async () => {
      try {
        const data = await apiGet('/api/strava/auth-url');
        window.location.href = data.auth_url;
      } catch (err) {
        console.error('Strava-Verbindung fehlgeschlagen:', err);
      }
    });
    actions.appendChild(connectBtn);
  } else {
    const syncBtn = document.createElement('button');
    syncBtn.className = 'strava-panel__button strava-panel__button--primary';
    syncBtn.textContent = 'Aktivitäten synchronisieren';
    syncBtn.addEventListener('click', async () => {
      syncBtn.disabled = true;
      syncBtn.textContent = 'Synchronisiere…';
      try {
        await apiPost('/api/activities/sync', {});
        await loadAllData();
      } catch (err) {
        console.error('Sync fehlgeschlagen:', err);
      } finally {
        syncBtn.disabled = false;
        syncBtn.textContent = 'Aktivitäten synchronisieren';
      }
    });
    actions.appendChild(syncBtn);
  }

  panel.appendChild(actions);

  // Ausklappbare Aktivitäten-Liste (standardmäßig eingeklappt)
  const details = document.createElement('details');
  details.className = 'strava-panel__details';
  details.open = false;

  const summary = document.createElement('summary');
  summary.className = 'strava-panel__summary';
  summary.textContent = 'Letzte 10 synchronisierte Aktivitäten';
  details.appendChild(summary);

  const list = document.createElement('div');
  list.className = 'strava-panel__list';
  details.appendChild(list);

  panel.appendChild(details);

  container.appendChild(panel);
}


function renderActivitiesList(listEl, activities) {
  listEl.innerHTML = '';

  if (activities.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'strava-panel__item';
    empty.textContent = 'Noch keine Aktivitäten synchronisiert.';
    listEl.appendChild(empty);
    return;
  }

  activities.slice(0, 10).forEach((activity) => {
    const item = document.createElement('div');
    item.className = 'strava-panel__item';

    const info = document.createElement('div');
    info.className = 'strava-panel__item-info';

    const name = document.createElement('div');
    name.className = 'strava-panel__item-name';
    name.textContent = activity.name;
    info.appendChild(name);

    const meta = document.createElement('div');
    meta.className = 'strava-panel__item-meta';
    const d = new Date(activity.start_date);
    meta.textContent = `${d.getDate()}.${d.getMonth() + 1}.${d.getFullYear()} · ${activity.activity_type}`;
    info.appendChild(meta);

    item.appendChild(info);

    const stats = document.createElement('span');
    stats.className = 'strava-panel__item-stats';
    const km = (activity.distance_m / 1000).toFixed(2);
    const minutes = Math.round(activity.moving_time_s / 60);
    const kcal = activity.calories != null ? `${Math.round(activity.calories)} kcal` : '';
    stats.textContent = kcal ? `${km} km · ${minutes} min · ${kcal}` : `${km} km · ${minutes} min`;
    item.appendChild(stats);


    listEl.appendChild(item);
  });
}

// ============================================================
// Kalender-Rendering
// ============================================================

function renderCalendar() {
  const app = document.getElementById('app');
  app.innerHTML = '';

  const calendar = document.createElement('div');
  calendar.className = 'calendar';

  // Toolbar
  const toolbar = document.createElement('header');
  toolbar.className = 'calendar__toolbar';

  // Navigation
  const nav = document.createElement('div');
  nav.className = 'calendar__nav';

  const prevBtn = document.createElement('button');
  prevBtn.className = 'calendar__button';
  prevBtn.textContent = '‹';
  prevBtn.setAttribute('aria-label', 'Zurück');
  prevBtn.addEventListener('click', () => navigate(-1));
  nav.appendChild(prevBtn);

  const nextBtn = document.createElement('button');
  nextBtn.className = 'calendar__button';
  nextBtn.textContent = '›';
  nextBtn.setAttribute('aria-label', 'Vor');
  nextBtn.addEventListener('click', () => navigate(1));
  nav.appendChild(nextBtn);

  const todayBtn = document.createElement('button');
  todayBtn.className = 'calendar__button calendar__button--today';
  todayBtn.textContent = 'Heute';
  todayBtn.addEventListener('click', () => {
    state.currentDate = new Date();
    state.selectedDate = new Date();
    loadMeals(state.selectedDate).then(() => renderCalendar());
  });
  nav.appendChild(todayBtn);


  toolbar.appendChild(nav);

  // Titel
  const title = document.createElement('h1');
  title.className = 'calendar__title';
  title.textContent = formatTitle(state.view, state.currentDate);
  toolbar.appendChild(title);

  // Ansichts-Buttons (Woche/Monat/Jahr)
  const views = document.createElement('div');
  views.className = 'calendar__views';

  const viewLabels = { week: 'Woche', month: 'Monat', year: 'Jahr' };
  Object.entries(viewLabels).forEach(([key, label]) => {
    const btn = document.createElement('button');
    btn.className = `calendar__view-button${state.view === key ? ' calendar__view-button--active' : ''}`;
    btn.textContent = label;
    btn.addEventListener('click', () => {
      state.view = key;
      renderCalendar();
    });
    views.appendChild(btn);
  });


  toolbar.appendChild(views);

  // Anzeige-Modus Toggle (Kalender/Liste)
  const modeToggle = document.createElement('div');
  modeToggle.className = 'calendar__mode-toggle';

  const calBtn = document.createElement('button');
  calBtn.className = `calendar__mode-button${state.displayMode === 'calendar' ? ' calendar__mode-button--active' : ''}`;
  calBtn.textContent = 'Kalender';
  calBtn.addEventListener('click', () => {
    state.displayMode = 'calendar';
    renderCalendar();
  });
  modeToggle.appendChild(calBtn);

  const listBtn = document.createElement('button');
  listBtn.className = `calendar__mode-button${state.displayMode === 'list' ? ' calendar__mode-button--active' : ''}`;
  listBtn.textContent = 'Liste';
  listBtn.addEventListener('click', () => {
    state.displayMode = 'list';
    renderCalendar();
  });
  modeToggle.appendChild(listBtn);

  toolbar.appendChild(modeToggle);

  // Logout-Button
  const logoutBtn = document.createElement('button');
  logoutBtn.className = 'calendar__button';
  logoutBtn.textContent = 'Abmelden';
  logoutBtn.addEventListener('click', logout);
  toolbar.appendChild(logoutBtn);

  calendar.appendChild(toolbar);


  // Body
  const body = document.createElement('main');
  body.className = 'calendar__body';

  if (state.displayMode === 'list') {
    // Listenansicht
    renderListView(body, state.currentDate, state.calendarItems);
  } else {
    // Kalenderansicht
    switch (state.view) {
      case 'week':
        renderWeekView(body, state.currentDate, state.calendarItems);
        break;
      case 'month':
        renderMonthView(body, state.currentDate, state.calendarItems);
        break;
      case 'year':
        renderYearView(body, state.currentDate, state.calendarItems);
        break;
    }

  }


  // Mahlzeiten-Panel (nur bei Woche/Monat in Kalenderansicht)
  if (state.displayMode === 'calendar' && state.view !== 'year') {
    renderMealsPanel(body, state.selectedDate);
  }


  // Strava-Panel
  renderStravaPanel(body);

  calendar.appendChild(body);
  app.appendChild(calendar);

  // Mahlzeiten-Liste füllen
  const listEl = body.querySelector('.meals-panel__list');
  const totalEl = body.querySelector('.meals-panel__total');
  if (listEl && totalEl) {
    renderMealsList(listEl, totalEl, state.meals);
  }

  // Aktivitäten-Liste füllen
  const actListEl = body.querySelector('.strava-panel__list');
  if (actListEl) {
    renderActivitiesList(actListEl, state.activities);
  }
}


function navigate(direction) {
  switch (state.view) {
    case 'week':
      state.currentDate = addDays(state.currentDate, direction * 7);
      break;
    case 'month':
      state.currentDate = addMonths(state.currentDate, direction);
      break;
    case 'year':
      state.currentDate = addYears(state.currentDate, direction);
      break;
  }
  renderCalendar();
}


// ============================================================
// Daten laden
// ============================================================

async function loadEvents() {
  try {
    state.events = await apiGet('/api/events');
  } catch (err) {
    console.error('Ereignisse laden fehlgeschlagen:', err);
    state.events = [];
  }
}

async function loadMeals(date) {
  try {
    const dateStr = toISODate(date);
    state.meals = await apiGet(`/api/meals/date/${dateStr}`);
  } catch (err) {
    console.error('Mahlzeiten laden fehlgeschlagen:', err);
    state.meals = [];
  }
}

async function loadActivities() {
  try {
    state.activities = await apiGet('/api/activities');
  } catch (err) {
    console.error('Aktivitäten laden fehlgeschlagen:', err);
    state.activities = [];
  }
}

async function loadCalendarItems() {
  try {
    const data = await apiGet('/api/calendar');
    state.calendarItems = data.items || [];
  } catch (err) {
    console.error('Kalenderdaten laden fehlgeschlagen:', err);
    state.calendarItems = [];
  }
}

async function loadStravaStatus() {
  try {
    const data = await apiGet('/api/strava/status');
    state.stravaAuthenticated = data.authenticated;
  } catch (err) {
    console.error('Strava-Status laden fehlgeschlagen:', err);
    state.stravaAuthenticated = false;
  }
}

async function loadAllData() {
  await Promise.all([
    loadEvents(),
    loadMeals(state.selectedDate),
    loadActivities(),
    loadCalendarItems(),
    loadStravaStatus(),
  ]);
  renderCalendar();
}


// ============================================================
// Authentifizierung
// ============================================================

async function checkAuth() {
  try {
    const data = await apiGet('/api/auth/status');
    state.auth.authenticated = data.authenticated;
    state.auth.user = data.user;
  } catch (err) {
    state.auth.authenticated = false;
    state.auth.user = null;
  }
}

function renderLoginScreen() {
  const app = document.getElementById('app');
  app.innerHTML = '';

  const login = document.createElement('div');
  login.className = 'login-screen';

  const card = document.createElement('div');
  card.className = 'login-card';

  const title = document.createElement('h1');
  title.className = 'login-card__title';
  title.textContent = 'TrainingsPlanner';
  card.appendChild(title);

  const subtitle = document.createElement('p');
  subtitle.className = 'login-card__subtitle';
  subtitle.textContent = 'Dein persönlicher Trainings- und Ernährungsplaner';
  card.appendChild(subtitle);

  const loginBtn = document.createElement('button');
  loginBtn.className = 'login-card__button';
  loginBtn.textContent = 'Mit Google anmelden';
  loginBtn.addEventListener('click', async () => {
    try {
      const data = await apiGet('/api/auth/google/auth-url');
      window.location.href = data.auth_url;
    } catch (err) {
      console.error('Google-Login fehlgeschlagen:', err);
      const error = document.createElement('p');
      error.className = 'login-card__error';
      error.textContent = `Login fehlgeschlagen: ${err.message}`;
      card.appendChild(error);
    }
  });
  card.appendChild(loginBtn);

  login.appendChild(card);
  app.appendChild(login);
}

async function handleGoogleCallback() {
  // Prüfen, ob wir einen Google-Code in der URL haben
  const urlParams = new URLSearchParams(window.location.search);
  const code = urlParams.get('code');

  if (code) {
    try {
      await apiPost('/api/auth/google/token', { code });
      // Code aus der URL entfernen
      window.history.replaceState({}, document.title, window.location.pathname);
      return true;
    } catch (err) {
      console.error('Google-Login fehlgeschlagen:', err);
      return false;
    }
  }
  return false;
}

async function logout() {
  try {
    await apiPost('/api/auth/logout', {});
  } catch (err) {
    console.error('Logout fehlgeschlagen:', err);
  }
  // Alle userbezogenen Zustände zurücksetzen, damit keine Daten des
  // vorherigen Benutzers in der UI verbleiben.
  state.auth.authenticated = false;
  state.auth.user = null;
  state.stravaAuthenticated = false;
  state.activities = [];
  state.events = [];
  state.meals = [];
  state.calendarItems = [];
  renderLoginScreen();
}


// ============================================================
// App starten
// ============================================================

async function init() {
  const app = document.getElementById('app');
  app.innerHTML = '<div class="app__status">Lade TrainingsPlanner…</div>';

  try {
    // Google-Callback verarbeiten (falls vorhanden)
    await handleGoogleCallback();

    // Auth-Status prüfen
    await checkAuth();

    if (!state.auth.authenticated) {
      renderLoginScreen();
      return;
    }

    await loadAllData();
  } catch (err) {
    app.innerHTML = `
      <div class="app__status app__status--error">
        <p>Die Anwendung konnte nicht geladen werden.</p>
        <p>${err.message}</p>
      </div>
    `;
  }
}

// Start
init();



