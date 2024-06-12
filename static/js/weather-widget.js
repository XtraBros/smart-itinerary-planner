// custom widget using data.gov.sg api
document.addEventListener('DOMContentLoaded', () => {   
    const weekday = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
    // URLs for the weather forecast APIs
    const twoHourForecastURL = 'https://api.data.gov.sg/v1/environment/2-hour-weather-forecast';
    const fourDayForecastURL = 'https://api.data.gov.sg/v1/environment/4-day-weather-forecast';
    const oneDayForecastURL = 'https://api.data.gov.sg/v1/environment/24-hour-weather-forecast';

    // Function to fetch weather data from the APIs
    const fetchWeatherData = async () => {
        try {
            // Fetch 2-hour weather forecast
            const twoHourResponse = await fetch(twoHourForecastURL);
            if (!twoHourResponse.ok) {
                throw new Error('Response Error for 2-hour forecast.');
            }
            const twoHourData = await twoHourResponse.json();

            // Fetch 4-day weather forecast
            const fourDayResponse = await fetch(fourDayForecastURL);
            if (!fourDayResponse.ok) {
                throw new Error('Response Error for 4-day forecast.');
            }
            const fourDayData = await fourDayResponse.json();

            const oneDayResponse = await fetch(oneDayForecastURL);
            if (!oneDayResponse.ok) {
                throw new Error('Response Error for 24-hour forecast.');
            }
            const oneDayData = await oneDayResponse.json();

            // Update the weather widget with both data
            updateWeatherWidget(twoHourData, oneDayData, fourDayData);
        } catch (error) {
            console.error('Error fetching weather data:', error);
        }
    };
    // Function to update the weather widget with fetched data
    const updateWeatherWidget = (twoHourData, oneDayData, fourDayData) => {
        // fill relevant html components with data from the API response
        const day = new Date(oneDayData.items[0].timestamp).getDay()
        document.getElementById('forecast0').textContent = twoHourData.items[0].forecasts.find(f => f.area.toLowerCase() === 'mandai')['forecast'];
        document.getElementById('forecast1').textContent = twoHourData.items[0].forecasts.find(f => f.area.toLowerCase() === 'mandai')['forecast'];
        document.getElementById('tempHigh0').textContent = `${oneDayData.items[0].general.temperature.high}\u00B0C`;
        document.getElementById('tempLow0').textContent = `${oneDayData.items[0].general.temperature.low}\u00B0C`;
        document.getElementById('tempHigh1').textContent = `${oneDayData.items[0].general.temperature.high}\u00B0C`;
        document.getElementById('tempLow1').textContent = `${oneDayData.items[0].general.temperature.low}\u00B0C`;
        document.getElementById('tempHigh2').textContent = `${fourDayData.items[0].forecasts[0].temperature.high}\u00B0C`;
        document.getElementById('tempLow2').textContent = `${fourDayData.items[0].forecasts[0].temperature.low}\u00B0C`;
        document.getElementById('tempHigh3').textContent = `${fourDayData.items[0].forecasts[1].temperature.high}\u00B0C`;
        document.getElementById('tempLow3').textContent = `${fourDayData.items[0].forecasts[1].temperature.low}\u00B0C`;
        document.getElementById('tempHigh4').textContent = `${fourDayData.items[0].forecasts[2].temperature.high}\u00B0C`;
        document.getElementById('tempLow4').textContent = `${fourDayData.items[0].forecasts[2].temperature.low}\u00B0C`;
        document.getElementById('datetext2').textContent = weekday[day+1]
        document.getElementById('datetext3').textContent = weekday[day+2]
        document.getElementById('datetext4').textContent = weekday[day+3]
        document.getElementById('weather-icon0').src = `static/icons/${getIcon(twoHourData.items[0].forecasts.find(f => f.area.toLowerCase() === 'mandai')['forecast'])}.png`
        document.getElementById('weather-icon1').src = `static/icons/${getIcon(twoHourData.items[0].forecasts.find(f => f.area.toLowerCase() === 'mandai')['forecast'])}.png`
        fetch('/weather_icon', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(fourDayData.items[0].forecasts[0].forecast)
        }).then(response => response.json()).then(data => {
            document.getElementById('weather-icon2').src = `static/icons/${getIcon(data)}.png`
        });
        fetch('/weather_icon', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(fourDayData.items[0].forecasts[1].forecast)
        }).then(response => response.json()).then(data => {
            document.getElementById('weather-icon3').src = `static/icons/${getIcon(data)}.png`
        });
        fetch('/weather_icon', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(fourDayData.items[0].forecasts[2].forecast)
        }).then(response => response.json()).then(data => {
            document.getElementById('weather-icon4').src = `static/icons/${getIcon(data)}.png`
        });
    };

    // Fetch weather data when the page loads
    fetchWeatherData();
});

function getIcon(forecast){
    lib ={'Fair': '22a', 'Fair (Day)': '22a', 'Fair (Night)': '22b', 'Fair and Warm': '24a', 'Partly Cloudy': '22a',
        'Partly Cloudy (Day)': '22a', 'Partly Cloudy (Night)': '22b', 'Cloudy': '23a', 'Hazy': '16', 'Slightly Hazy': '16',
        'Windy': '26', 'Mist': '16', 'Fog': '16', 'Light Rain': '15', 'Moderate Rain': '12', 'Heavy Rain': '9', 'Passing Showers': '11',
        'Light Showers': '11', 'Showers': '12', 'Heavy Showers': '9', 'Thundery Showers': '2', 'Heavy Thundery Showers': '2',
        'Heavy Thundery Showers with Gusty Winds': '2'}
    return lib[forecast]
};