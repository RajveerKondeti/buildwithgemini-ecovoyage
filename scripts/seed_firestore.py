from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-01-ee290fd2683c"
db = firestore.Client(project=PROJECT_ID)

trips = [
    {
        "name": "Costa Rica Eco-Retreat",
        "description": "A 5-day stay at an eco-lodge in the rainforest with sustainable tours.",
        "cost": 1200
    },
    {
        "name": "Swiss Alps Glamping",
        "description": "Glamping in the Swiss Alps featuring carbon-neutral facilities.",
        "cost": 2500
    }
]

for trip in trips:
    doc_ref = db.collection("trips").document(trip["name"].replace(" ", "_").lower())
    doc_ref.set(trip)

print("Firestore seeded successfully with trips.")
