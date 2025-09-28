using System;
using System.Collections.Generic;
using UnityEngine;

[Serializable]
public class SimpleShipData
{
    public ShipInfo ship_info;
    public PlacementStats placement_stats;
    public List<PlacedBlock> placed_blocks;
}

[Serializable]
public class ShipInfo
{
    public string name;
    public ShipDimensions dimensions;
    public ShipGridInfo grid_info;
    public ShipConstraints constraints;
}

[Serializable]
public class ShipDimensions
{
    public float width;      // 미터 단위 (120m)
    public float height;     // 미터 단위 (80m) 
    public float grid_unit;  // 그리드 해상도 (0.5m)
}

[Serializable]
public class ShipGridInfo
{
    public int grid_count_width;   // 240 (그리드 개수)
    public int grid_count_height;  // 160 (그리드 개수)
}

[Serializable]
public class ShipConstraints
{
    public int bow_clearance;
    public int stern_clearance;
    public int block_spacing;
}

[Serializable]
public class PlacementStats
{
    public int total_blocks;
    public int placed_count;
}

[Serializable]
public class PlacedBlock
{
    public string id;
    public string type;
    public BlockPosition2D position;  // 2D 위치만 필요
    public BlockDimensions dimensions;
    public VoxelData voxel_data;  // 배치된 복셀 데이터
    public object transform;  // object로 받아서 수동 파싱
}

[Serializable]
public class BlockPosition2D
{
    public float x;
    public float y;
}

[Serializable]
public class BlockDimensions
{
    public float width;
    public float height;
}

[Serializable]
public class VoxelData
{
    public float grid_resolution;  // 그리드 해상도 (0.5m)
    public List<PositionedVoxel> positioned_voxels;  // 배치된 복셀들
    public int total_voxels;  // 총 복셀 개수
}

[Serializable]
public class PositionedVoxel
{
    public int x;  // Unity X 좌표 (그리드 단위)
    public int y;  // Unity Z 좌표 (그리드 단위, Python Y → Unity Z 변환됨)
    public List<float> height_info;  // [min_height, max_height] 형태 (그리드 단위)
}

[Serializable]
public class FlatTransform
{
    // Position
    public float px, py, pz;
    // Rotation  
    public float rx, ry, rz;
    // Scale
    public float sx, sy, sz;
    
    public Vector3 GetPosition() { return new Vector3(px, py, pz); }
    public Vector3 GetRotation() { return new Vector3(rx, ry, rz); }
    public Vector3 GetScale() { return new Vector3(sx, sy, sz); }
}