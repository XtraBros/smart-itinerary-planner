document.addEventListener('DOMContentLoaded', () => {
    // const resizer = document.getElementById('resizer');
    const rightPanel = document.getElementById('right-panel');
    // const map = document.getElementById('map');
    // const zoomCtrls = document.getElementById('zoom-controls');
    const popupModal = document.getElementById('popupModal');
    const btn = document.getElementById("robotIcoId");
    const tishiDom = document.getElementById('tishi')
    const poiSwiper = document.getElementById('poiSwiper')
    btn.onclick = function () {
        popupModal.style.display = "block";
        tishiDom.style.display = "none";
        localStorage.setItem('isFirstOpen', true)
    }
    window.onclick = function (event) {
        poiSwiper.style.display = 'none';
      if (event.target === popupModal) {
        popupModal.style.display = "none";
      }
    }
    let isResizing = false;

    // resizer.addEventListener('mousedown', (e) => {
    //     isResizing = true;
    //     document.addEventListener('mousemove', onMouseMove);
    //     document.addEventListener('mouseup', onMouseUp);
    // });

    const onMouseMove = (e) => {
        if (!isResizing) return;

        // Calculate new widths in percentages
        // const containerWidth = document.getElementById('container').clientWidth;
        // const newRightPanelWidthPercentage = ((containerWidth - e.clientX) / containerWidth) * 100;
        // const newMapWidthPercentage = 100 - newRightPanelWidthPercentage - ((resizer.offsetWidth / containerWidth) * 100);
        // const zoomControlsRightPercentage = newRightPanelWidthPercentage + 3;

        // Set the new widths and positions in percentages
        // rightPanel.style.width = `${newRightPanelWidthPercentage}%`;
        // map.style.width = `${newMapWidthPercentage}%`;
        // resizer.style.right = `${newRightPanelWidthPercentage}%`;
        // zoomCtrls.style.right = `${zoomControlsRightPercentage}%`;

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
document.addEventListener('DOMContentLoaded', function() {
    // const rightPanel = document.getElementById('right-panel');
    // const zoomControls = document.getElementById('zoom-controls');
    // const resizer = document.getElementById('resizer');

    function adjustZoomControls() {
        // const containerWidth = document.getElementById('container').offsetWidth;
        // const rightPanelWidth = rightPanel.offsetWidth;
        // const threePercentWidth = containerWidth * 0.02; // Calculate 3% of the container's width
        // const zoomControlRight = rightPanelWidth + threePercentWidth;

        // zoomControls.style.right = `${zoomControlRight}px`;
    }

    // Initial adjustment
    adjustZoomControls();

    // Adjust when the window is resized
    window.addEventListener('resize', adjustZoomControls);

    // Adjust when the resizer is moved
    // resizer.addEventListener('mousedown', function() {
    //     document.addEventListener('mousemove', adjustZoomControls);
    //     document.addEventListener('mouseup', function() {
    //         document.removeEventListener('mousemove', adjustZoomControls);
    //     }, { once: true });
    // });
});