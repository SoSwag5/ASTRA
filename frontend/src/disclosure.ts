/**
 * Animated opening and closing for native <details> and for button-controlled
 * regions (beta 3).
 *
 * The native element keeps its semantics: <summary> (or the button) stays the
 * keyboard control, and the browser still reports expanded or collapsed. The
 * movement is a height and opacity animation through the Web Animations API,
 * so it works without `interpolate-size` or `::details-content`.
 *
 * - Interruptible: a new toggle starts from the height the content has
 *   actually reached, in the new direction, and the older animation is
 *   cancelled. Its completion can no longer change anything.
 * - Closing content stays rendered only until its animation ends, and is
 *   inert meanwhile, so focus cannot move into something that is leaving.
 * - Reduced motion (OS or ASTRA), or a browser without element.animate,
 *   toggles at once. Nothing is ever delayed to wait for motion.
 */
export type DisclosureSurface = {
  /** Whether the content is rendered now (details.open, or !region.hidden). */
  shown(): boolean;
  show(value: boolean): void;
  body: HTMLElement;
};

export type DisclosureOptions = {
  reduced: () => boolean;
  /** Called at once with the new intended state, before any animation. */
  onIntent?: (open: boolean) => void;
  openMs?: number;
  closeMs?: number;
};

export type DisclosureController = {
  toggle(next?: boolean): void;
  /** Adopt a change the browser made itself (find-in-page, assistive tech). */
  sync(): void;
  destroy(): void;
  readonly open: boolean;
  readonly animating: boolean;
};

const OPEN_EASE = 'cubic-bezier(0.22, 0.8, 0.24, 1)';
const CLOSE_EASE = 'cubic-bezier(0.4, 0, 1, 1)';

export function createDisclosure(surface: DisclosureSurface, options: DisclosureOptions): DisclosureController {
  const {body} = surface;
  let target = surface.shown();
  let running: Animation | null = null;

  const rest = () => {
    body.style.overflow = '';
    body.inert = false;
  };

  function toggle(next = !target) {
    if (next === target) return;
    // Measure before cancelling: this is where the content visibly is now.
    const from = surface.shown() ? body.getBoundingClientRect().height : 0;
    const previous = running;
    running = null;
    previous?.cancel();
    target = next;
    options.onIntent?.(next);
    if (next) surface.show(true);

    const canAnimate = typeof body.animate === 'function' && !options.reduced();
    const full = canAnimate ? body.scrollHeight : 0;
    const to = next ? full : 0;
    if (!canAnimate || from === to) {
      if (!next) surface.show(false);
      rest();
      return;
    }
    const base = next ? options.openMs ?? 260 : options.closeMs ?? 200;
    const share = Math.abs(to - from) / Math.max(full, 1);
    const duration = Math.round(base * Math.max(0.4, Math.min(1, share)));
    const visible = (height: number) => full > 0 ? Math.min(1, height / full) : 0;
    body.style.overflow = 'hidden';
    if (!next && body.contains(document.activeElement)) {
      (body.parentElement?.querySelector('summary') as HTMLElement | null)?.focus();
    }
    body.inert = !next;
    const animation = body.animate(
      [{height: `${from}px`, opacity: visible(from)}, {height: `${to}px`, opacity: next ? 1 : 0}],
      {duration, easing: next ? OPEN_EASE : CLOSE_EASE, fill: 'forwards'});
    running = animation;
    animation.onfinish = () => {
      if (running !== animation) return;
      running = null;
      if (!target) surface.show(false);
      animation.cancel();
      rest();
    };
  }

  return {
    toggle,
    sync() {
      if (running || surface.shown() === target) return;
      target = surface.shown();
      options.onIntent?.(target);
    },
    destroy() {
      const previous = running;
      running = null;
      previous?.cancel();
    },
    get open() { return target; },
    get animating() { return running !== null; },
  };
}
