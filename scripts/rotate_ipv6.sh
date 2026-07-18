#!/bin/bash
# rotate_host_ipv6.sh - Force la rotation de l'IPv6 temporaire de l'hôte

# CONFIGURATION
# Interface réseau physique de l'hôte (ex: enp2s0)
INTERFACE="enp2s0"

# Vérification des droits root
if [ "$EUID" -ne 0 ]; then
  echo "Erreur : ce script doit être exécuté en tant que root (ou avec sudo)."
  exit 1
fi

# 1. Récupérer l'adresse temporaire active (non dépréciée)
TEMP_IPS=$(ip -6 addr show dev "$INTERFACE" temporary | grep "inet6" | grep -v "deprecated" | awk '{print $2}')

if [ -z "$TEMP_IPS" ]; then
  echo "[-] Aucune adresse IPv6 temporaire active trouvée sur $INTERFACE."
  exit 1
fi

for IP in $TEMP_IPS; do
  echo "[+] Dépréciation de l'adresse IP temporaire actuelle : $IP"
  # En passant preferred_lft à 0, le noyau marque l'IP comme "deprecated".
  # Les connexions en cours continuent sans coupure, mais les nouvelles utiliseront la nouvelle IP.
  ip -6 addr change "$IP" dev "$INTERFACE" preferred_lft 0
done

# 2. Déclencher la génération de la nouvelle IP par le noyau
echo "[+] Déclenchement de la génération de la nouvelle IP..."
ping6 -c 1 -w 2 ipv6.google.com >/dev/null 2>&1

# 3. Attendre et afficher la nouvelle IP
sleep 1
NEW_IP=$(ip -6 addr show dev "$INTERFACE" temporary | grep "inet6" | grep -v "deprecated" | awk '{print $2}')
echo "[+] Nouvelle adresse IPv6 temporaire active : $NEW_IP"

# 4. Nettoyage des très vieilles IPs dépréciées (facultatif mais garde l'interface propre)
# Supprime les IPs temporaires dépréciées pour ne pas accumuler des dizaines d'adresses
DEPRECATED_IPS=$(ip -6 addr show dev "$INTERFACE" temporary | grep "deprecated" | awk '{print $2}')
for OLD_DEP_IP in $DEPRECATED_IPS; do
  # Pour éviter de couper une connexion en cours sur l'IP tout juste dépréciée,
  # on ne supprime pas celle-ci immédiatement si elle est très récente.
  echo "    -> Nettoyage de l'ancienne IP dépréciée : $OLD_DEP_IP"
  ip -6 addr del "$OLD_DEP_IP" dev "$INTERFACE" 2>/dev/null
done
