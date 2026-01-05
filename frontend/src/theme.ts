export type ThemePreference = 'light' | 'dark' | 'system';

const THEME_STORAGE_KEY = 'video_summariser_theme_preference';

let systemListenerCleanup: (() => void) | null = null;

function isThemePreference(value: unknown): value is ThemePreference {
  return value === 'light' || value === 'dark' || value === 'system';
}

export function getStoredThemePreference(): ThemePreference {
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY);
    if (isThemePreference(raw)) return raw;
  } catch {
    // ignore
  }
  return 'system';
}

export function setStoredThemePreference(pref: ThemePreference): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, pref);
  } catch {
    // ignore
  }
}

function prefersDark(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function applyDarkClass(shouldDark: boolean): void {
  const root = document.documentElement;
  root.classList.toggle('dark', shouldDark);
  // Helps native form controls, scrollbars, etc.
  root.style.colorScheme = shouldDark ? 'dark' : 'light';
}

function ensureSystemListener(): void {
  if (systemListenerCleanup) return;
  if (!window.matchMedia) return;

  const mql = window.matchMedia('(prefers-color-scheme: dark)');
  const handler = () => {
    // Only react to system changes when preference is system.
    if (getStoredThemePreference() === 'system') {
      applyDarkClass(mql.matches);
    }
  };

  if (typeof mql.addEventListener === 'function') {
    mql.addEventListener('change', handler);
    systemListenerCleanup = () => mql.removeEventListener('change', handler);
  } else {
    // Safari < 14
    (mql as MediaQueryList & { addListener: (cb: () => void) => void }).addListener(handler);
    systemListenerCleanup = () =>
      (mql as MediaQueryList & { removeListener: (cb: () => void) => void }).removeListener(handler);
  }
}

function removeSystemListener(): void {
  systemListenerCleanup?.();
  systemListenerCleanup = null;
}

export function applyThemePreference(pref: ThemePreference): void {
  if (pref === 'system') {
    ensureSystemListener();
    applyDarkClass(prefersDark());
    return;
  }
  removeSystemListener();
  applyDarkClass(pref === 'dark');
}

export function initTheme(): void {
  applyThemePreference(getStoredThemePreference());
}


