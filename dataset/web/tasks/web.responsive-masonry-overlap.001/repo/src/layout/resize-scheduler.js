export function createResizeScheduler(runLayout, observedElement) {
  let scheduled = false;
  let timerId = null;

  const requestLayout = () => {
    if (scheduled) {
      return;
    }

    scheduled = true;
    timerId = window.setTimeout(() => {
      runLayout();
      scheduled = false;
      timerId = null;
    }, 0);
  };

  const observer = new ResizeObserver(requestLayout);

  return {
    start() {
      window.addEventListener("resize", requestLayout);
      observer.observe(observedElement);
      requestLayout();
    },
    request: requestLayout,
    destroy() {
      window.removeEventListener("resize", requestLayout);
      observer.disconnect();
      if (timerId !== null) {
        window.clearTimeout(timerId);
      }
      scheduled = false;
      timerId = null;
    }
  };
}
