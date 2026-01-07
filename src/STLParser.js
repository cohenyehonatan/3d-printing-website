/**
 * STL Parser - Client-side parsing of binary and ASCII STL files
 * Provides basic analysis without server-side trimesh
 */

const STLParser = {
  /**
   * Parse an STL file and extract basic statistics
   */
  async parse(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      
      reader.onload = (e) => {
        try {
          const buffer = e.target.result;
          const view = new DataView(buffer);
          
          // Check if binary STL (must be at least 84 bytes for header + triangle count)
          const isBinary = buffer.byteLength >= 84;
          
          if (isBinary && this.isBinarySTL(buffer, view)) {
            const stats = this.parseBinarySTL(buffer, view);
            resolve(stats);
          } else {
            // Try ASCII STL
            const stats = this.parseASCIISTL(buffer);
            resolve(stats);
          }
        } catch (error) {
          reject(new Error(`Failed to parse STL: ${error.message}`));
        }
      };
      
      reader.onerror = () => {
        reject(new Error('Failed to read file'));
      };
      
      reader.readAsArrayBuffer(file);
    });
  },

  /**
   * Check if buffer is likely a binary STL file
   */
  isBinarySTL(buffer, view) {
    if (buffer.byteLength < 84) return false;
    
    // Read number of triangles at byte 80
    const numTriangles = view.getUint32(80, true);
    
    // Expected size: 80 (header) + 4 (triangle count) + 50 * numTriangles
    const expectedSize = 84 + 50 * numTriangles;
    
    // Check if actual size matches expected size (with small tolerance)
    return Math.abs(buffer.byteLength - expectedSize) < 100;
  },

  /**
   * Parse binary STL file
   */
  parseBinarySTL(buffer, view) {
    const numTriangles = view.getUint32(80, true);
    
    let minX = Infinity, maxX = -Infinity;
    let minY = Infinity, maxY = -Infinity;
    let minZ = Infinity, maxZ = -Infinity;
    
    // Parse triangles (each triangle is 50 bytes)
    let offset = 84;
    
    for (let i = 0; i < numTriangles; i++) {
      // Skip normal vector (12 bytes)
      offset += 12;
      
      // Read vertices (3 vertices, 3 floats each)
      for (let v = 0; v < 3; v++) {
        const x = view.getFloat32(offset, true);
        const y = view.getFloat32(offset + 4, true);
        const z = view.getFloat32(offset + 8, true);
        
        minX = Math.min(minX, x);
        maxX = Math.max(maxX, x);
        minY = Math.min(minY, y);
        maxY = Math.max(maxY, y);
        minZ = Math.min(minZ, z);
        maxZ = Math.max(maxZ, z);
        
        offset += 12;
      }
      
      // Skip attribute byte count (2 bytes)
      offset += 2;
    }
    
    // Convert from mm to cm
    const dimX = (maxX - minX) / 10;
    const dimY = (maxY - minY) / 10;
    const dimZ = (maxZ - minZ) / 10;
    
    // Estimate volume using bounding box (crude approximation)
    const volume = (dimX * dimY * dimZ);
    
    return {
      triangles: numTriangles,
      volume: volume,
      bounding_box: {
        x: dimX * 10, // mm
        y: dimY * 10, // mm
        z: dimZ * 10  // mm
      },
      complexity: numTriangles > 10000 ? 'High' : numTriangles > 5000 ? 'Medium' : 'Low'
    };
  },

  /**
   * Parse ASCII STL file
   */
  parseASCIISTL(buffer) {
    const text = new TextDecoder().decode(buffer);
    
    // Count facets
    const facets = text.match(/facet\s+normal/gi) || [];
    const numTriangles = facets.length;
    
    // Extract vertices to find bounding box
    const vertices = [];
    const vertexPattern = /vertex\s+([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)\s+([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)\s+([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)/g;
    
    let match;
    while ((match = vertexPattern.exec(text)) !== null) {
      vertices.push({
        x: parseFloat(match[1]),
        y: parseFloat(match[3]),
        z: parseFloat(match[5])
      });
    }
    
    if (vertices.length === 0) {
      throw new Error('No vertices found in STL file');
    }
    
    // Calculate bounding box
    let minX = Infinity, maxX = -Infinity;
    let minY = Infinity, maxY = -Infinity;
    let minZ = Infinity, maxZ = -Infinity;
    
    vertices.forEach(v => {
      minX = Math.min(minX, v.x);
      maxX = Math.max(maxX, v.x);
      minY = Math.min(minY, v.y);
      maxY = Math.max(maxY, v.y);
      minZ = Math.min(minZ, v.z);
      maxZ = Math.max(maxZ, v.z);
    });
    
    // Convert from mm to cm
    const dimX = (maxX - minX) / 10;
    const dimY = (maxY - minY) / 10;
    const dimZ = (maxZ - minZ) / 10;
    
    // Estimate volume
    const volume = dimX * dimY * dimZ;
    
    return {
      triangles: numTriangles,
      volume: volume,
      bounding_box: {
        x: dimX * 10, // mm
        y: dimY * 10, // mm
        z: dimZ * 10  // mm
      },
      complexity: numTriangles > 10000 ? 'High' : numTriangles > 5000 ? 'Medium' : 'Low'
    };
  }
};

export default STLParser;
