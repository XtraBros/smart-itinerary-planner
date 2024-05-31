document.addEventListener('DOMContentLoaded', () => {
    const resizer = document.getElementById('resizer');
    const leftPanel = document.getElementById('left-panel');
    const map = document.getElementById('map');

    let isResizing = false;

    resizer.addEventListener('mousedown', (e) => {
        isResizing = true;
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    });

    const onMouseMove = (e) => {
        if (!isResizing) return;

        // Calculate new widths
        const containerOffsetLeft = document.getElementById('container').offsetLeft;
        const newMapWidth = e.clientX - containerOffsetLeft;
        const newLeftPanelWidth = document.getElementById('container').clientWidth - newMapWidth - resizer.offsetWidth;

        // Set the new widths
        map.style.width = `${newMapWidth}px`;
        leftPanel.style.width = `${newLeftPanelWidth}px`;
        // Trigger map resize
        if (window.mapboxMap) {
            window.mapboxMap.resize();
        }
    };
    
    const onMouseUp = () => {
        isResizing = false;
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
    };
});
