-- Verifica la migracion 020 con el rol de la aplicacion, motel_app: un celular se vincula solo a una estadia en curso y
-- una sola vez, el vinculo solo se revoca (una vez y a nombre del usuario de la sesion), no se borra antes de los 30
-- dias, entra el aviso VINCULO y otro establecimiento no ve nada. Corre en una transaccion que se revierte.
-- Uso: psql -v ON_ERROR_STOP=1 -d <base con las migraciones aplicadas> -f db/verify_qr_fijo.sql  (como dueno)
SET app.establecimiento_id = '1';
BEGIN;
DO $$
DECLARE
    otro integer;
    conserje integer;
    ajeno integer;
    categoria integer;
    tarifa integer;
    habitacion integer;
    habitacion_dos integer;
    guardia integer;
    turno uuid;
    turno_cerrado uuid;
    vinculo bigint;
    filas integer;
    bloqueado boolean;
BEGIN
    INSERT INTO establecimientos (codigo, nombre) VALUES ('verif-qr', 'Otro') RETURNING id INTO otro;
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol) VALUES ('verif.q', 'Conserje', 'x', 'OPERADOR')
    RETURNING id INTO conserje;
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol) VALUES ('verif.q2', 'Otro', 'x', 'OPERADOR')
    RETURNING id INTO ajeno;
    INSERT INTO categorias_habitacion (nombre) VALUES ('Verif QR') RETURNING id INTO categoria;
    INSERT INTO tarifas (nombre, tarifa_base, estadia_base_min, tolerancia_min, fraccion_min, tarifa_fraccion, vigente, categoria_id)
    VALUES ('Verif QR', 8000, 120, 0, 30, 2500, true, categoria) RETURNING id INTO tarifa;
    INSERT INTO habitaciones (numero, estado, categoria_id) VALUES (9931, 'Ocupada', categoria) RETURNING id INTO habitacion;
    INSERT INTO habitaciones (numero, estado, categoria_id) VALUES (9932, 'Libre', categoria) RETURNING id INTO habitacion_dos;
    INSERT INTO guardias (operador_id, franja) VALUES (conserje, '06:00') RETURNING id INTO guardia;
    INSERT INTO turnos (id, habitacion_id, tarifa_id, tipo_cliente, hora_inicio, estado, tarifa_base, total_general,
                        operador_apertura_id, guardia_apertura_id)
    VALUES (gen_random_uuid(), habitacion, tarifa, 'Auto', now(), 'En Curso', 8000, 8000, conserje, guardia)
    RETURNING id INTO turno;
    ALTER TABLE turnos DISABLE TRIGGER USER;
    INSERT INTO turnos (id, habitacion_id, tarifa_id, tipo_cliente, hora_inicio, hora_fin, estado, tarifa_base, total_general,
                        operador_apertura_id, guardia_apertura_id, operador_cierre_id)
    VALUES (gen_random_uuid(), habitacion_dos, tarifa, 'Auto', now(), now(), 'FINALIZADO', 8000, 8000, conserje, guardia, conserje)
    RETURNING id INTO turno_cerrado;
    ALTER TABLE turnos ENABLE TRIGGER USER;
    PERFORM set_config('app.operador_id', conserje::text, true);

    SET LOCAL ROLE motel_app;

    -- 1. La version del QR arranca en 1 y se puede cambiar; nunca baja de 1.
    SELECT qr_version INTO filas FROM habitaciones WHERE id = habitacion;
    IF filas <> 1 THEN RAISE EXCEPTION 'La version del QR no arranca en 1'; END IF;
    UPDATE habitaciones SET qr_version = qr_version + 1 WHERE id = habitacion;
    bloqueado := false;
    BEGIN UPDATE habitaciones SET qr_version = 0 WHERE id = habitacion;
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'La version del QR quedo en 0'; END IF;

    -- 2. Un celular se vincula a una estadia en curso, una sola vez; a una cerrada, no.
    INSERT INTO vinculos_cliente (turno_id, huella, origen) VALUES (turno, repeat('a', 64), 'QR') RETURNING id INTO vinculo;
    bloqueado := false;
    BEGIN INSERT INTO vinculos_cliente (turno_id, huella, origen) VALUES (turno, repeat('a', 64), 'INVITADO');
    EXCEPTION WHEN unique_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'El mismo celular se vinculo dos veces a la estadia'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO vinculos_cliente (turno_id, huella, origen) VALUES (turno_cerrado, repeat('b', 64), 'QR');
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se vinculo un celular a una estadia cerrada'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO vinculos_cliente (turno_id, huella, origen) VALUES (turno, 'no-es-una-huella', 'QR');
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro una huella mal formada'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO vinculos_cliente (turno_id, huella, origen, revocado_en, revocado_por_id)
    VALUES (turno, repeat('c', 64), 'QR', now(), conserje);
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un vinculo ya revocado'; END IF;

    -- 3. Solo se revoca, a nombre del usuario de la sesion y una vez; la huella no cambia.
    bloqueado := false;
    BEGIN UPDATE vinculos_cliente SET huella = repeat('d', 64) WHERE id = vinculo;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Cambio la huella de un vinculo'; END IF;
    bloqueado := false;
    BEGIN UPDATE vinculos_cliente SET revocado_en = now(), revocado_por_id = ajeno WHERE id = vinculo;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se revoco un vinculo a nombre de otro'; END IF;
    UPDATE vinculos_cliente SET revocado_en = now(), revocado_por_id = conserje WHERE id = vinculo;
    bloqueado := false;
    BEGIN UPDATE vinculos_cliente SET revocado_en = now(), revocado_por_id = conserje WHERE id = vinculo;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se revoco dos veces un vinculo'; END IF;

    -- 4. Un vinculo reciente no se borra.
    bloqueado := false;
    BEGIN DELETE FROM vinculos_cliente WHERE id = vinculo;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se borro un vinculo antes de los 30 dias'; END IF;

    -- 5. El aviso «no veo mi estadia» entra como pedido del cliente.
    INSERT INTO pedidos_cliente (turno_id, tipo) VALUES (turno, 'VINCULO');

    -- 6. Otro establecimiento no ve los vinculos.
    PERFORM set_config('app.establecimiento_id', otro::text, true);
    SELECT count(*) INTO filas FROM vinculos_cliente;
    IF filas <> 0 THEN RAISE EXCEPTION 'Un establecimiento vio los vinculos de otro'; END IF;
    RAISE NOTICE 'verify_qr_fijo: version del QR, vinculo a estadia en curso, revocacion unica, retencion, aviso y aislamiento verificados';
END $$;
ROLLBACK;
