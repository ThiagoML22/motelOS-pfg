-- Verifica la migracion 015 con el rol de la aplicacion, motel_app: el camino de un pedido no vuelve atras, los avisos con
-- dato son coherentes, quien lleva o atiende queda a nombre de la sesion, una calificacion por turno, dentro de su tiempo,
-- sin borrarse y cada establecimiento ve solo las suyas. Corre en una transaccion que se revierte.
-- Uso: psql -v ON_ERROR_STOP=1 -d <base con las migraciones aplicadas> -f db/verify_cliente_ampliado.sql  (como dueno)
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
    habitacion_tres integer;
    guardia integer;
    turno uuid;
    reciente uuid;
    viejo uuid;
    articulo integer;
    pedido integer;
    filas integer;
    bloqueado boolean;
BEGIN
    INSERT INTO establecimientos (codigo, nombre) VALUES ('verif-cli2', 'Otro') RETURNING id INTO otro;
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol) VALUES ('verif.d', 'Conserje', 'x', 'OPERADOR')
    RETURNING id INTO conserje;
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol) VALUES ('verif.d2', 'Otro', 'x', 'OPERADOR')
    RETURNING id INTO ajeno;
    INSERT INTO categorias_habitacion (nombre) VALUES ('Verif cliente 2') RETURNING id INTO categoria;
    INSERT INTO tarifas (nombre, tarifa_base, estadia_base_min, tolerancia_min, fraccion_min, tarifa_fraccion, vigente, categoria_id)
    VALUES ('Verif cliente 2', 8000, 120, 0, 30, 2500, true, categoria) RETURNING id INTO tarifa;
    INSERT INTO habitaciones (numero, estado, categoria_id) VALUES (9931, 'Ocupada', categoria) RETURNING id INTO habitacion;
    INSERT INTO habitaciones (numero, estado, categoria_id) VALUES (9932, 'Libre', categoria) RETURNING id INTO habitacion_dos;
    INSERT INTO habitaciones (numero, estado, categoria_id) VALUES (9933, 'Libre', categoria) RETURNING id INTO habitacion_tres;
    INSERT INTO guardias (operador_id, franja) VALUES (conserje, '06:00') RETURNING id INTO guardia;
    INSERT INTO articulos (codigo, descripcion, precio_unitario, stock_actual) VALUES ('VERIF-D', 'Agua', 800, 3)
    RETURNING id INTO articulo;
    INSERT INTO turnos (id, habitacion_id, tarifa_id, tipo_cliente, hora_inicio, estado, tarifa_base, total_general,
                        operador_apertura_id, guardia_apertura_id)
    VALUES (gen_random_uuid(), habitacion, tarifa, 'Auto', now(), 'En Curso', 8000, 8000, conserje, guardia)
    RETURNING id INTO turno;
    ALTER TABLE turnos DISABLE TRIGGER USER;
    INSERT INTO turnos (id, habitacion_id, tarifa_id, tipo_cliente, hora_inicio, hora_fin, estado, tarifa_base, total_general,
                        operador_apertura_id, guardia_apertura_id, operador_cierre_id)
    VALUES (gen_random_uuid(), habitacion_dos, tarifa, 'Auto', now() - interval '3 hours', now() - interval '10 minutes',
            'FINALIZADO', 8000, 8000, conserje, guardia, conserje)
    RETURNING id INTO reciente;
    INSERT INTO turnos (id, habitacion_id, tarifa_id, tipo_cliente, hora_inicio, hora_fin, estado, tarifa_base, total_general,
                        operador_apertura_id, guardia_apertura_id, operador_cierre_id)
    VALUES (gen_random_uuid(), habitacion_tres, tarifa, 'Auto', now() - interval '6 hours', now() - interval '3 hours',
            'FINALIZADO', 8000, 8000, conserje, guardia, conserje)
    RETURNING id INTO viejo;
    ALTER TABLE turnos ENABLE TRIGGER USER;
    PERFORM set_config('app.operador_id', conserje::text, true);

    SET LOCAL ROLE motel_app;

    -- 1. Un carrito: varias lineas con el mismo lote.
    INSERT INTO pedidos_cliente (turno_id, tipo, articulo_id, cantidad, lote)
    VALUES (turno, 'ARTICULO', articulo, 2, '11111111-1111-1111-1111-111111111111') RETURNING id INTO pedido;

    -- 2. Los avisos con dato son coherentes.
    INSERT INTO pedidos_cliente (turno_id, tipo, minutos) VALUES (turno, 'TIEMPO', 60);
    INSERT INTO pedidos_cliente (turno_id, tipo, medio_pago) VALUES (turno, 'SALIDA', 'POSNET');
    bloqueado := false;
    BEGIN INSERT INTO pedidos_cliente (turno_id, tipo, minutos) VALUES (turno, 'TIEMPO', 45);
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entraron minutos fuera de las opciones'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO pedidos_cliente (turno_id, tipo) VALUES (turno, 'TIEMPO');
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un aviso de tiempo sin minutos'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO pedidos_cliente (turno_id, tipo, medio_pago) VALUES (turno, 'SALIDA', 'CHEQUE');
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un medio de pago desconocido'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO pedidos_cliente (turno_id, tipo, medio_pago) VALUES (turno, 'TOALLAS', 'EFECTIVO');
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un medio de pago en un aviso que no es la cuenta'; END IF;

    -- 3. Llevarlo queda a nombre de la sesion.
    bloqueado := false;
    BEGIN UPDATE pedidos_cliente SET estado = 'En camino', llevado_por_id = ajeno, llevado_en = now() WHERE id = pedido;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se llevo un pedido a nombre de otro'; END IF;
    bloqueado := false;
    BEGIN UPDATE pedidos_cliente SET estado = 'En camino' WHERE id = pedido;
    EXCEPTION WHEN check_violation OR raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Quedo en camino sin saber quien lo lleva'; END IF;
    UPDATE pedidos_cliente SET estado = 'En camino', llevado_por_id = conserje, llevado_en = now() WHERE id = pedido;

    -- 4. No vuelve atras, y lo pedido no cambia.
    bloqueado := false;
    BEGIN UPDATE pedidos_cliente SET estado = 'Pendiente', llevado_por_id = NULL, llevado_en = NULL WHERE id = pedido;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Un pedido volvio atras'; END IF;
    bloqueado := false;
    BEGIN UPDATE pedidos_cliente SET lote = NULL WHERE id = pedido;
    EXCEPTION WHEN insufficient_privilege OR raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se cambio lo pedido'; END IF;

    -- 5. Se entrega una vez.
    bloqueado := false;
    BEGIN UPDATE pedidos_cliente SET estado = 'Atendido', atendido_por_id = ajeno, atendido_en = now() WHERE id = pedido;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se entrego un pedido a nombre de otro'; END IF;
    UPDATE pedidos_cliente SET estado = 'Atendido', atendido_por_id = conserje, atendido_en = now() WHERE id = pedido;
    bloqueado := false;
    BEGIN UPDATE pedidos_cliente SET estado = 'Rechazado' WHERE id = pedido;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se atendio dos veces un pedido'; END IF;

    -- 6. Se califica en curso o poco despues, una vez por turno.
    INSERT INTO calificaciones (turno_id, habitacion_id, puntaje, problemas) VALUES (turno, habitacion, 2, 4 + 2);
    INSERT INTO calificaciones (turno_id, habitacion_id, puntaje) VALUES (reciente, habitacion_dos, 5);
    bloqueado := false;
    BEGIN INSERT INTO calificaciones (turno_id, habitacion_id, puntaje) VALUES (turno, habitacion, 1);
    EXCEPTION WHEN unique_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entraron dos calificaciones en un turno'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO calificaciones (turno_id, habitacion_id, puntaje) VALUES (viejo, habitacion_tres, 1);
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se califico una estadia vieja'; END IF;

    -- 7. La habitacion es la del turno y el puntaje tiene rango.
    bloqueado := false;
    BEGIN INSERT INTO calificaciones (turno_id, habitacion_id, puntaje) VALUES (viejo, habitacion, 3);
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se califico otra habitacion'; END IF;
    PERFORM set_config('app.operador_id', conserje::text, true);
    bloqueado := false;
    BEGIN INSERT INTO calificaciones (turno_id, habitacion_id, puntaje) VALUES (viejo, habitacion_tres, 6);
    EXCEPTION WHEN check_violation OR raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un puntaje fuera de rango'; END IF;

    -- 8. No se cambia ni se borra.
    bloqueado := false;
    BEGIN UPDATE calificaciones SET puntaje = 5 WHERE turno_id = turno;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se cambio una calificacion'; END IF;
    bloqueado := false;
    BEGIN DELETE FROM calificaciones WHERE turno_id = turno;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se borro una calificacion'; END IF;

    -- 9. Otro establecimiento no ve las del 1.
    PERFORM set_config('app.establecimiento_id', otro::text, true);
    SELECT count(*) INTO filas FROM calificaciones;
    IF filas <> 0 THEN RAISE EXCEPTION 'Un establecimiento vio las calificaciones de otro'; END IF;
    RAISE NOTICE 'verify_cliente_ampliado: camino del pedido, avisos coherentes, calificacion unica y aislamiento verificados';
END $$;
ROLLBACK;
