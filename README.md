# autowalter
# Pompe

il faut sectionner le cable rouge mais garder le cable noir intact, la pompe se branche toujours en usb. les deux bouts du cable rouge sont mis sur le relais pour pouvoir controller le passage du courant par le RPI. 

- Le cable rouge vers la pompe se connecte à COM
- le cable rouge vers le port USB se connecte à NO
- NC reste vide

Ce qui donne, quand on regarde d’en haut avec les vis vers le haut : 

Pompe    USB
          |        |
NC       COM       NO
|        |         | 
S        +         —
|        |         |
G4       D1        D3

# Relais
DRT slot 1 : relais rouge 5V 
DRT slot 3 : relais noir 
GCH slot 4 : relais Signal

# Moisture sensor
DRT Slot 5 : Sensor Rouge 3.3V
DRT Slot 8 : Sensor Noir 
DRT Slot 10 : Sensor Signal
