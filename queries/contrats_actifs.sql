-- Contrats actifs par client — appelée par l'assistant
-- pour répondre à « avec qui avons-nous des contrats actifs ? ».

SELECT
    cl.raison_sociale,
    COUNT(c.id) AS nb_contrats_actifs,
    SUM(c.montant_ht) AS montant_total_ht
FROM contrats c
JOIN clients cl ON cl.id = c.client_id
WHERE c.statut = 'actif'
GROUP BY cl.raison_sociale
ORDER BY nb_contrats_actifs DESC;
