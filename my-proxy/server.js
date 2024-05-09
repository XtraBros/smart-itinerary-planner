const express = require('express');
const cors = require('cors');
const axios = require('axios');

const app = express();
const PORT = 3000;

app.use(cors());

app.get('/tile', async (req, res) => {
    const url = req.query.url;

    try {
        const response = await axios.get(url, {
            responseType: 'arraybuffer',
            timeout: 30000
        });

        res.setHeader('Content-Type', 'image/png');
        res.send(response.data);
    } catch (error) {
        console.error('Error fetching tile:', { url, error: error.message });
        res.status(500).json({
            type: 'error',
            message: error.message
        });
    }
});

app.listen(PORT, () => {
    console.log(`Server is running on http://localhost:${PORT}`);
});