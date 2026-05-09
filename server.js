const express = require('express');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = 5000;

// Serve static files
app.use(express.static('.'));

// API endpoint to serve stories
app.get('/api/stories', (req, res) => {
  try {
    const storiesPath = path.join(__dirname, 'data', 'stories.json');
    const data = JSON.parse(fs.readFileSync(storiesPath, 'utf8'));
    res.json(data);
  } catch (err) {
    console.error('Error reading stories:', err);
    res.status(500).json({ error: 'Failed to load today\'s folly.' });
  }
});

// Fallback to index.html
app.get('/{*splat}', (req, res) => {
  res.sendFile('index.html', { root: '.' });
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`The Daily Misanthrope is judging humanity on port ${PORT}`);
});
