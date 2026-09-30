-- db/init.sql

CREATE TABLE habitaciones (
    id SERIAL PRIMARY KEY,
    numero INTEGER UNIQUE NOT NULL,
    estado VARCHAR(20) NOT NULL CHECK (estado IN ('Libre', 'Ocupada', 'En Limpieza', 'Mantenimiento'))
);

CREATE TABLE turnos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    habitacion_id INTEGER NOT NULL REFERENCES habitaciones(id),
    identificador_vehicular VARCHAR(50),
    tipo_cliente VARCHAR(20) NOT NULL DEFAULT 'Auto' CHECK (tipo_cliente IN ('Auto', 'Moto', 'Peaton')),
    hora_inicio TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    hora_fin TIMESTAMP WITH TIME ZONE,
    tarifa_base NUMERIC(10, 2) NOT NULL DEFAULT 12000,
    total_sobreturno NUMERIC(10, 2) NOT NULL DEFAULT 0,
    total_consumos NUMERIC(10, 2) NOT NULL DEFAULT 0,
    total_general NUMERIC(10, 2) NOT NULL DEFAULT 12000,
    estado VARCHAR(20) NOT NULL CHECK (estado IN ('En Curso', 'FINALIZADO', 'Anulado'))
);

CREATE TABLE articulos (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(50) UNIQUE NOT NULL,
    descripcion VARCHAR(255) NOT NULL,
    precio_unitario NUMERIC(10, 2) NOT NULL,
    stock_actual INTEGER NOT NULL CHECK (stock_actual >= 0),
    categoria VARCHAR(50)
);

CREATE TABLE detalles_consumo (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    turno_id UUID NOT NULL REFERENCES turnos(id),
    articulo_id INTEGER NOT NULL REFERENCES articulos(id),
    cantidad INTEGER NOT NULL CHECK (cantidad > 0),
    precio_unitario NUMERIC(10, 2) NOT NULL,
    subtotal NUMERIC(10, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE pagos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    turno_id UUID NOT NULL REFERENCES turnos(id),
    monto NUMERIC(10, 2) NOT NULL,
    medio_pago VARCHAR(50) NOT NULL CHECK (medio_pago IN ('EFECTIVO', 'MERCADO_PAGO', 'POSNET')),
    comprobante_referencia VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Habilitar RLS (Row Level Security)
ALTER TABLE habitaciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE turnos ENABLE ROW LEVEL SECURITY;
ALTER TABLE articulos ENABLE ROW LEVEL SECURITY;
ALTER TABLE detalles_consumo ENABLE ROW LEVEL SECURITY;
ALTER TABLE pagos ENABLE ROW LEVEL SECURITY;

CREATE POLICY all_habitaciones ON habitaciones FOR ALL USING (true);
CREATE POLICY all_turnos ON turnos FOR ALL USING (true);
CREATE POLICY all_articulos ON articulos FOR ALL USING (true);
CREATE POLICY all_detalles_consumo ON detalles_consumo FOR ALL USING (true);
CREATE POLICY all_pagos ON pagos FOR ALL USING (true);

-- Disparador para asegurar inmutabilidad de turnos cerrados/anulados (Append-Only Log)
CREATE OR REPLACE FUNCTION check_turno_inmutable()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.estado IN ('FINALIZADO', 'Anulado') THEN
        RAISE EXCEPTION 'RN-RES-01: No se puede modificar un turno finalizado o anulado.';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_check_turno_inmutable
BEFORE UPDATE ON turnos
FOR EACH ROW
EXECUTE FUNCTION check_turno_inmutable();

-- Seeds iniciales
INSERT INTO habitaciones (numero, estado) VALUES 
(1, 'Libre'), (2, 'Libre'), (3, 'Libre'), (4, 'Libre'), (5, 'Libre'), 
(6, 'Libre'), (7, 'Libre'), (8, 'Libre'), (9, 'Libre'), (10, 'Libre'), 
(11, 'Libre'), (12, 'Libre'), (13, 'Libre');

INSERT INTO articulos (codigo, descripcion, precio_unitario, stock_actual, categoria) VALUES
('MIN-001', 'Agua Mineral 500ml', 800, 10, 'Bebidas'),
('MIN-002', 'Bebida Energética', 1200, 8, 'Bebidas'),
('MIN-003', 'Cerveza Lata 473ml', 1800, 12, 'Bebidas'),
('SNA-001', 'Papas Fritas Lays 90g', 1500, 5, 'Snacks');
