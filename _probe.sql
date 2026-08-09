\echo === total users ===
SELECT count(*) FROM users;
\echo === total ads ===
SELECT count(*) FROM ads;
\echo === total ad_images ===
SELECT count(*) FROM ad_images;
\echo === seed ads ===
SELECT count(*) FROM ads WHERE source='seed';
\echo === seed users that have a seed ad ===
SELECT count(DISTINCT a.user_id) FROM ads a WHERE a.source='seed' AND a.user_id IS NOT NULL;
\echo === users with no ads ===
SELECT count(*) FROM users u WHERE NOT EXISTS (SELECT 1 FROM ads a WHERE a.user_id = u.id);
\echo === colliding usernames (non-seed, matching seed usernames) ===
SELECT DISTINCT u.username
FROM users u
JOIN ads a_seed ON a_seed.user_id = u.id
WHERE a_seed.source = 'seed'
  AND u.username ILIKE '%seed%' ESCAPE '';
\echo === sample seed usernames ===
SELECT u.id, u.username, u.telegram_id, a.source, a.status
FROM users u
JOIN ads a ON a.user_id = u.id
WHERE a.source = 'seed'
LIMIT 15;
\echo === status/source distribution ===
SELECT source, status, count(*) FROM ads GROUP BY source, status ORDER BY source, status;
\echo === unique usernames like seed ===
SELECT count(DISTINCT username) FROM users WHERE username ILIKE '%seed%';
