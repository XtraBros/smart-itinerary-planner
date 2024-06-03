document.addEventListener('DOMContentLoaded', () => {
    const resizer = document.getElementById('resizer');
    const rightPanel = document.getElementById('right-panel');
    const map = document.getElementById('map');
    const zoomCtrls = document.getElementById('zoom-controls');

    let isResizing = false;

    resizer.addEventListener('mousedown', (e) => {
        isResizing = true;
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    });

    const onMouseMove = (e) => {
        if (!isResizing) return;

        // Calculate new widths in percentages
        const containerWidth = document.getElementById('container').clientWidth;
        const newRightPanelWidthPercentage = ((containerWidth - e.clientX) / containerWidth) * 100;
        const newMapWidthPercentage = 100 - newRightPanelWidthPercentage - ((resizer.offsetWidth / containerWidth) * 100);
        const zoomControlsRightPercentage = newRightPanelWidthPercentage + 3;

        // Set the new widths and positions in percentages
        rightPanel.style.width = `${newRightPanelWidthPercentage}%`;
        map.style.width = `${newMapWidthPercentage}%`;
        resizer.style.right = `${newRightPanelWidthPercentage}%`;
        zoomCtrls.style.right = `${zoomControlsRightPercentage}%`;

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
