-- Top sessions par nombre de stagiaires sur Q3 (juillet-septembre)
-- de l'année courante.
--
-- Branchée et fonctionnelle — sert de référence aux autres requêtes.

SELECT
    s.code,
    s.titre,
    s.date_debut,
    COUNT(st.id) AS nb_stagiaires
FROM sessions s
LEFT JOIN stagiaires st ON st.session_id = s.id
WHERE EXTRACT(MONTH FROM s.date_debut) BETWEEN 7 AND 9
GROUP BY s.id, s.code, s.titre, s.date_debut
ORDER BY nb_stagiaires DESC, s.date_debut DESC
LIMIT 10;
