/**
 * Transitions between whole views (#47 visual revision).
 *
 * Page changes, Settings section changes, layout changes and closing a drawer
 * or dialog run inside a View Transition, so the old view is a still image
 * that leaves while the new one arrives: nothing old stays mounted, no effect
 * or request runs twice, and focus and scroll are handled by the update
 * itself. Without browser support, or when motion is reduced, the update
 * simply runs. The CSS for each kind is in motion.css.
 */
import {flushSync} from 'react-dom';

export type TransitionKind = 'page' | 'section' | 'dismiss' | 'confirm' | 'layout';
export type Direction = 'forward' | 'back';

type ViewChange = {finished: Promise<void>; ready: Promise<void>; skipTransition: () => void};
type TransitionDocument = Document & {startViewTransition?: (update: () => void) => ViewChange};

export function motionReduced(): boolean {
  if (typeof document === 'undefined') return true;
  if (document.documentElement.dataset.motion === 'full') return false;
  return document.documentElement.dataset.motion === 'reduced'
    || Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
}

export function supportsViewTransitions(): boolean {
  return typeof document !== 'undefined' && typeof (document as TransitionDocument).startViewTransition === 'function';
}

let current = 0;
let active: {view: ViewChange; apply: () => void} | undefined;

/** The next interaction takes priority over a decorative snapshot. */
export function installMotionInterrupts(): () => void {
  const finish = () => active?.view.skipTransition();
  const events = ['pointerdown', 'keydown', 'wheel'] as const;
  events.forEach(event => document.addEventListener(event, finish, {capture: true, passive: true}));
  const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
  const changed = () => { if (preference.matches) finish(); };
  preference.addEventListener('change', changed);
  return () => {
    events.forEach(event => document.removeEventListener(event, finish, {capture: true}));
    preference.removeEventListener('change', changed);
    finish();
  };
}

/**
 * Run `update` exactly once, animated when possible, then `after` once the
 * new view is in the DOM (to move focus into it). A transition started while
 * another runs replaces it; the earlier update still applies.
 */
export function transition(kind: TransitionKind, update: () => void, direction: Direction = 'forward', after?: () => void): void {
  const doc = document as TransitionDocument;
  const root = document.documentElement;
  const ticket = ++current;
  // A skipped transition still invokes its update callback. Commit it now,
  // once, so it cannot overwrite a newer synchronous/reduced-motion update.
  active?.apply();
  active?.view.skipTransition();
  active = undefined;
  delete root.dataset.vt;
  delete root.dataset.vtDirection;
  if (!supportsViewTransitions() || motionReduced() || document.visibilityState !== 'visible') {
    flushSync(update);
    after?.();
    return;
  }
  root.dataset.vt = kind;
  root.dataset.vtDirection = direction;
  let ran = false;
  const apply = () => { if (!ran) { ran = true; flushSync(update); if (ticket === current) after?.(); } };
  try {
    const view = doc.startViewTransition!(apply);
    active = {view, apply};
    view.ready.catch(() => {}); // Skipping animation is a normal interaction.
    view.finished.catch(() => {}).finally(() => {
      if (ticket === current) { active = undefined; delete root.dataset.vt; delete root.dataset.vtDirection; }
    });
  } catch {
    delete root.dataset.vt; delete root.dataset.vtDirection;
    apply();
  }
}

/** Which way a move between two positions in an ordered list goes. */
export function directionBetween(order: readonly string[], from: string, to: string): Direction {
  const a = order.indexOf(from), b = order.indexOf(to);
  return a >= 0 && b >= 0 && b < a ? 'back' : 'forward';
}

/**
 * What a person actually gets. "Match system" follows the operating system;
 * "Reduce motion" stays still. "Full motion" is an explicit opt-in override.
 */
export type MotionMode = 'full' | 'reduced-by-astra' | 'reduced-by-system';
export function motionMode(choice: string, systemReduced: boolean): MotionMode {
  if (choice === 'full') return 'full';
  if (choice === 'reduced') return 'reduced-by-astra';
  return systemReduced ? 'reduced-by-system' : 'full';
}

/**
 * Only the newest request may apply its answer. A slower, older response is
 * dropped, so rapid period changes always settle on the last choice.
 */
export function latestGate() {
  let current = 0;
  return {
    begin: () => ++current,
    isCurrent: (ticket: number) => ticket === current,
  };
}

/**
 * A short "these numbers changed" settle on elements that were updated by the
 * person's own request. It starts from where any earlier settle had reached,
 * never delays the data, and does nothing under reduced motion.
 */
export function settle(elements: Iterable<Element>): void {
  if (motionReduced()) return;
  for (const element of elements) {
    if (typeof (element as HTMLElement).animate !== 'function') continue;
    element.getAnimations?.().forEach(animation => { if (animation.id === 'astra-settle') animation.cancel(); });
    const animation = (element as HTMLElement).animate(
      [{opacity: 0.45, transform: 'translateY(6px)'}, {opacity: 1, transform: 'none'}],
      {duration: 300, easing: 'cubic-bezier(0.22, 0.8, 0.24, 1)'});
    animation.id = 'astra-settle';
  }
}
