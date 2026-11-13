// Copy this file to test/export_level_test.dart inside sidhant947/ScrewJam.
// Then run it with Flutter to emit one source snapshot as a marked JSON line.

import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:screwjam/models/game_models.dart';
import 'package:screwjam/services/level_generator.dart';

Offset _globalHolePosition(PlateModel plate, ScrewHoleModel hole) {
  final cosA = cos(plate.angle);
  final sinA = sin(plate.angle);
  return plate.position +
      Offset(
        hole.relativeOffset.dx * cosA - hole.relativeOffset.dy * sinA,
        hole.relativeOffset.dx * sinA + hole.relativeOffset.dy * cosA,
      );
}

bool _pointInsidePlate(Offset point, PlateModel plate) {
  final relative = point - plate.position;
  final cosA = cos(-plate.angle);
  final sinA = sin(-plate.angle);
  final local = Offset(
    relative.dx * cosA - relative.dy * sinA,
    relative.dx * sinA + relative.dy * cosA,
  );
  return getPlatePath(plate).contains(local);
}

List<Map<String, String>> _computeCoverage(List<PlateModel> plates) {
  const screwRadius = 15.0;
  final offsets = <Offset>[Offset.zero];
  for (var i = 0; i < 8; i++) {
    final angle = i * pi / 4;
    offsets.add(Offset(cos(angle) * screwRadius, sin(angle) * screwRadius));
    offsets.add(
      Offset(
        cos(angle) * screwRadius * 0.65,
        sin(angle) * screwRadius * 0.65,
      ),
    );
  }

  final result = <Map<String, String>>[];
  for (var targetIndex = 0; targetIndex < plates.length; targetIndex++) {
    final targetPlate = plates[targetIndex];
    for (final hole in targetPlate.holes) {
      if (hole.currentScrew == null) continue;
      final global = _globalHolePosition(targetPlate, hole);

      for (var blockerIndex = 0; blockerIndex < plates.length; blockerIndex++) {
        final blocker = plates[blockerIndex];
        if (blocker.id == targetPlate.id) continue;
        final isHigher = blocker.layer > targetPlate.layer ||
            (blocker.layer == targetPlate.layer && blockerIndex > targetIndex);
        if (!isHigher) continue;

        if (offsets.any((offset) => _pointInsidePlate(global + offset, blocker))) {
          result.add({'plate_id': blocker.id, 'screw_id': hole.id});
        }
      }
    }
  }
  return result;
}

void main() {
  test('export one generated level as JSON', () {
    const levelNumber = int.fromEnvironment('LEVEL', defaultValue: 1);
    const seedValue = int.fromEnvironment('SEED', defaultValue: -1);
    const waitingCapacity = int.fromEnvironment('WAITING_CAPACITY', defaultValue: 4);

    final state = LevelGenerator.generateLevel(
      levelNumber,
      seed: seedValue < 0 ? null : seedValue,
      waitingCapacityOverride: waitingCapacity,
    );

    final boxes = [state.activeBox, ...state.pendingBoxes];
    final payload = {
      'name': seedValue < 0
          ? 'ScrewJam level $levelNumber'
          : 'ScrewJam level $levelNumber seed $seedValue',
      'metadata': {
        'level': levelNumber,
        'seed': seedValue < 0 ? null : seedValue,
        'source_commit': '5ee0b84970eba12d4fd7f937bae162bf75ba61f3',
      },
      'waiting_capacity': state.waitingHolesCapacity,
      'plates': [
        for (var order = 0; order < state.plates.length; order++)
          {
            'id': state.plates[order].id,
            'shape_type': state.plates[order].shapeType.name,
            'width': state.plates[order].size.width,
            'height': state.plates[order].size.height,
            'layer': state.plates[order].layer,
            'order': order,
            'x': state.plates[order].position.dx,
            'y': state.plates[order].position.dy,
            'angle': state.plates[order].angle,
            'holes': [
              for (final hole in state.plates[order].holes)
                {
                  'id': hole.id,
                  'dx': hole.relativeOffset.dx,
                  'dy': hole.relativeOffset.dy,
                  'color': hole.currentScrew?.name,
                },
            ],
          },
      ],
      'boxes': [
        for (final box in boxes)
          {
            'color': box.targetColor.name,
            'capacity': box.capacity,
            'collected': [for (final screw in box.collected) screw.name],
          },
      ],
      // Export exact Flutter Path.contains results so the Python archive does
      // not depend on its deterministic curved-path approximation.
      'covers': _computeCoverage(state.plates),
    };

    // The marker lets extract_snapshot.py ignore Flutter test-runner output.
    // ignore: avoid_print
    print('OSRP_SOURCE_SNAPSHOT:${jsonEncode(payload)}');
  });
}

