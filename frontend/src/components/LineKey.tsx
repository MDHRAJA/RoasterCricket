import { Icon } from './Signs';

export function LineKey({
  selected,
  matchAvailable,
  onFixtures,
  onMatch,
  labSelected = false,
  onLab,
  recordSelected = false,
  onRecord,
  onCommand,
  theme,
  onTheme,
}: {
  selected: boolean;
  matchAvailable: boolean;
  onFixtures: () => void;
  onMatch: () => void;
  labSelected?: boolean;
  onLab: () => void;
  recordSelected?: boolean;
  onRecord: () => void;
  onCommand: () => void;
  theme: string;
  onTheme: () => void;
}) {
  return (
    <aside className="line-key" aria-label="Main navigation">
      <a className="brand" href="#/fixtures?season=2026" aria-label="The Concourse, Fixtures">
        <svg width="34" height="34" viewBox="0 0 48 48" aria-hidden="true">
          <path d="M8 8h32v8H16v16h24v8H8Z" fill="currentColor" />
          <path d="M24 20h16v8H24Z" fill="currentColor" />
        </svg>
      </a>
      <nav className="places">
        <button
          className={`place ${!selected && !labSelected && !recordSelected ? 'active' : ''}`}
          onClick={onFixtures}
          aria-current={!selected && !labSelected && !recordSelected ? 'page' : undefined}
        >
          <span className="place-number">1</span>
          <span className="place-label">Fixtures</span>
        </button>
        <button
          className={`place ${selected ? 'active' : ''}`}
          onClick={onMatch}
          disabled={!matchAvailable}
          aria-current={selected ? 'page' : undefined}
          title={!matchAvailable ? 'Select a match from the board' : 'Open Match workspace'}
        >
          <span className="place-number">2</span>
          <span className="place-label">Match</span>
        </button>
        <button
          className={`place ${labSelected ? 'active' : ''}`}
          onClick={onLab}
          aria-current={labSelected ? 'page' : undefined}
          title="Open Lab"
        >
          <span className="place-number">3</span>
          <span className="place-label">Lab</span>
        </button>
        <button
          className={`place ${recordSelected ? 'active' : ''}`}
          onClick={onRecord}
          aria-current={recordSelected ? 'page' : undefined}
          title="Open Record"
        >
          <span className="place-number">4</span>
          <span className="place-label">Record</span>
        </button>
      </nav>
      <div className="rail-tools">
        <button
          className="icon-button"
          onClick={onTheme}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
        >
          <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
        </button>
        <button
          className="command-key"
          onClick={onCommand}
          aria-label="Open search, Control or Command K"
        >
          ⌘ K
        </button>
        <span className="rail-edition">IPL / 04</span>
      </div>
    </aside>
  );
}
