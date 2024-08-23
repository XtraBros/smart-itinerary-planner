let startx, starty;
function getAngle(angx, angy) {
    return Math.atan2(angy, angx) * 180 / Math.PI;
};

function getDirection(startx, starty, endx, endy) {
    const angx = endx - startx;
    const angy = endy - starty;
    let result = 0;

    //如果滑动距离太短
    if (Math.abs(angx) < 2 && Math.abs(angy) < 2) {
        return result;
    }

    const angle = getAngle(angx, angy);
    if (angle >= -135 && angle <= -45) {
        result = 1;
    } else if (angle > 45 && angle < 135) {
        result = 2;
    } else if ((angle >= 135 && angle <= 180) || (angle >= -180 && angle < -135)) {
        result = 3;
    } else if (angle >= -45 && angle <= 45) {
        result = 4;
    }
    return result;
}

document.addEventListener("touchstart", function (e) {
    startx = e.touches[0].pageX;
    starty = e.touches[0].pageY;
}, false);

document.addEventListener("touchend", function (e) {
    const popupModal = document.getElementById("popupModal");
    const poiSwiper = document.getElementById('poiSwiper')
    let endx, endy;
    endx = e.changedTouches[0].pageX;
    endy = e.changedTouches[0].pageY;
    const direction = getDirection(startx, starty, endx, endy);
    switch (direction) {
        case 0:
            // alert("未滑动！");
            break;
        case 1:
            // alert("向上！")
            break;
        case 2:
            if (popupModal) {
                popupModal.style.display = "none";
            }
            poiSwiper.style.display = 'none';
            // alert("向下！")
            break;
        case 3:
            // alert("向左！")
            break;
        case 4:
            // alert("向右！")
            break;
        default:
    }
}, false);