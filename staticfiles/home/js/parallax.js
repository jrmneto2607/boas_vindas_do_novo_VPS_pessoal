const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
let spaceFramePending = false;

function updateSpaceBackground() {
    const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
        document.body.style.setProperty(
        "--space-travel",
        `${Math.max(240, maxScroll * 0.05)}px`
    );
    const progress = maxScroll > 0
        ? Math.min(1, Math.max(0, window.scrollY / maxScroll))
        : 0;

    document.body.style.setProperty(
        "--space-offset",
        `${reducedMotion.matches ? 0 : window.scrollY * 0.05}px`
    );

    spaceFramePending = false;
}

window.addEventListener("scroll", () => {
    if (!spaceFramePending) {
        spaceFramePending = true;
        requestAnimationFrame(updateSpaceBackground);
    }
}, { passive: true });

window.addEventListener("resize", updateSpaceBackground);
reducedMotion.addEventListener("change", updateSpaceBackground);
updateSpaceBackground();