from .connection import get_connection

PESTS = [
    ('rice-planthopper', 'Rice Planthopper', 'Nilaparvata lugens', 'Rice', 'Feeds on rice plant sap and can cause yellowing, drying, and hopperburn.', 'Yellowing patches, wilting plants, and drying from the base upward.', 'HIGH', 'https://images.unsplash.com/photo-1530507629858-e4977d30e9e0?auto=format&fit=crop&w=900&q=82'),
    ('stem-borer', 'Stem Borer', 'Scirpophaga incertulas', 'Rice & maize', 'Larvae tunnel into stems, weakening young crops and producing dead hearts or white ears.', 'Dead hearts in young plants or white ears during later crop stages.', 'HIGH', 'https://images.unsplash.com/photo-1592982537447-6f2a6a0a3f7f?auto=format&fit=crop&w=900&q=82'),
    ('aphid', 'Aphid', 'Aphidoidea', 'Vegetables', 'Small sap-feeding insects that cluster on tender growth and may spread plant viruses.', 'Clusters under leaves, curled growth, sticky honeydew, and weak new shoots.', 'MEDIUM', 'https://images.unsplash.com/photo-1518531933037-91b2f5f229cc?auto=format&fit=crop&w=900&q=82'),
    ('fruit-fly', 'Fruit Fly', 'Tephritidae', 'Fruit crops', 'Adults lay eggs in developing fruit, where larvae damage the flesh and reduce crop quality.', 'Punctured fruit, soft spots, premature decay, and larvae inside fruit.', 'MEDIUM', 'https://images.unsplash.com/photo-1596568359553-a56de6974f37?auto=format&fit=crop&w=900&q=82'),
    ('armyworm', 'Armyworm', 'Spodoptera litura', 'Field crops', 'Caterpillars feed quickly across leaves and can move through crop rows in groups.', 'Irregular leaf holes, skeletonized foliage, and rapid defoliation.', 'HIGH', 'https://images.unsplash.com/photo-1535930749574-1399327ce78f?auto=format&fit=crop&w=900&q=82'),
    ('leaf-hopper', 'Leaf Hopper', 'Cicadellidae', 'Rice & vegetables', 'Sap-feeding insects that cause stippling and may transmit disease between plants.', 'Fine stippling, curled leaves, and reduced plant vigor.', 'LOW', 'https://images.unsplash.com/photo-1531266752426-aad472b7bbf4?auto=format&fit=crop&w=900&q=82'),
]

SOLUTIONS = [
    ('rice-planthopper', 'Rice Planthopper', 'HIGH', 'Rice', 'Yellowing patches, wilting plants, and drying from the base upward.', 'Inspect affected crop areas and follow the recommended integrated pest management procedure.', 'Keep field scouting regular, maintain balanced nutrients, and support beneficial insects.'),
    ('stem-borer', 'Stem Borer', 'HIGH', 'Rice & maize', 'Dead hearts in young plants or white ears during later crop stages.', 'Mark affected rows, remove heavily damaged material, and consult a validated crop protection guide.', 'Use field sanitation and monitor crop stages where stem borer activity is commonly observed.'),
    ('aphid', 'Aphid', 'MEDIUM', 'Vegetables', 'Clusters under leaves, curled growth, sticky honeydew, and weak new shoots.', 'Inspect new growth and use an integrated approach after confirming the pest and crop condition.', 'Encourage natural predators and avoid excessive nitrogen that promotes tender growth.'),
]


def seed_reference_data():
    with get_connection() as connection:
        connection.executemany('''INSERT OR IGNORE INTO pests (id, name, scientific_name, affected_crop, description, symptoms, risk, image) VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', PESTS)
        connection.executemany('''INSERT OR IGNORE INTO solutions (pest_id, pest_name, risk, affected_crop, symptoms, recommended_action, prevention) VALUES (?, ?, ?, ?, ?, ?, ?)''', SOLUTIONS)
        connection.commit()
